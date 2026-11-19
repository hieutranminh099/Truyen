"""Local Ollama + opt-in OpenAI-compatible cloud provider. No third-party pip packages."""
from __future__ import annotations
import json
import re
import socket
import threading
import time
import urllib.error
import urllib.request
from .config import Settings


class ProviderError(RuntimeError): pass


def decode_model_text(text: str) -> str:
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.S|re.I)
    # Some nonthinking models emit the literal reasoning delimiter.
    return text.strip()


def json_from_text(raw: str):
    s = decode_model_text(raw)
    try: return json.loads(s)
    except json.JSONDecodeError:
        match = re.search(r'```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```', s, re.S|re.I)
        if match: return json.loads(match.group(1))
        opener = s.find('{'); closer=s.rfind('}')
        if opener >= 0 and closer > opener: return json.loads(s[opener:closer+1])
        raise ValueError('AI không trả JSON hợp lệ')


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def http_json(url, payload, headers=None, timeout=600):
    body = json.dumps(payload, ensure_ascii=False).encode('utf8')
    req = urllib.request.Request(url, body, headers={'Content-Type':'application/json', **(headers or {})}, method='POST')
    try:
        with urllib.request.build_opener(_NoRedirect()).open(req, timeout=timeout) as response:
            return json.load(response)
    except urllib.error.HTTPError as e:
        e.close()
        raise ProviderError(f'HTTP {e.code} tại nhà cung cấp') from None
    except (urllib.error.URLError, socket.timeout, TimeoutError, OSError, ValueError):
        raise ProviderError('Không thể kết nối AI hoặc phản hồi không hợp lệ') from None


class AI:
    def __init__(self, settings=None):
        self.settings = settings or Settings()
        self._ollama_lock = threading.Lock()

    def chat(self, system: str, user: str, *, role='writer', cloud=False, temperature=0.7,
             max_tokens=None, structured=False, history=None):
        if cloud:
            return self._cloud(system,user,temperature,max_tokens or self.settings.tokens,structured,history)
        with self._ollama_lock:
            return self._ollama(system,user,temperature,max_tokens or self.settings.tokens,structured,history)

    def _ollama(self,system,user,temperature,max_tokens,structured,history):
        settings=self.settings
        msgs = [{'role':'system','content':system}] + (history or []) + [{'role':'user','content':user}]
        payload = {'model':settings.model,'stream':False,'think':False,'messages':msgs,
                   'options':{'num_ctx':settings.ctx,'num_predict':max_tokens,'temperature':temperature,'top_p':.91}}
        seed = getattr(settings, 'seed', None)
        if seed is not None:
            payload['options']['seed'] = seed
        if structured: payload['format']='json'
        last=None
        for n in range(2):
            try:
                result=http_json(settings.ollama_url+'/api/chat',payload,timeout=900)
                raw=decode_model_text(result.get('message',{}).get('content',''))
                if not raw: raise ProviderError('Ollama trả nội dung rỗng')
                return raw
            except ProviderError as e:
                last=e
                if n==0: time.sleep(.6)
        raise last

    def _cloud(self,system,user,temperature,max_tokens,structured,history):
        s=self.settings
        if not s.cloud_enabled:
            raise ProviderError('Cloud bị tắt. Thiết lập NOVEL_CLOUD_ENABLED=1 rồi chủ động chọn API trên giao diện.')
        msgs=[{'role':'system','content':system}]+(history or [])+[{'role':'user','content':user}]
        payload={'model':s.cloud_model,'messages':msgs,'stream':False,'temperature':temperature,'max_tokens':max_tokens}
        # Many OpenAI-compatible providers differ on JSON mode. Explicit prompt and parsing is safer.
        if structured: payload['messages'][0]['content'] += '\nBẮT BUỘC xuất JSON hợp lệ, không có markdown.'
        result=http_json(s.cloud_url+'/chat/completions',payload,
                         headers={'Authorization':'Bearer '+s.cloud_key},timeout=s.cloud_timeout)
        try: raw=result['choices'][0]['message']['content']
        except (KeyError,IndexError,TypeError): raise ProviderError('Cloud API trả cấu trúc không hỗ trợ')
        if isinstance(raw,list): raw='\n'.join(x.get('text','') for x in raw if isinstance(x,dict))
        raw=decode_model_text(str(raw))
        if not raw: raise ProviderError('Cloud trả nội dung rỗng')
        return raw

    def embed(self,text: str):
        if not text.strip(): raise ValueError('Không tạo embedding cho chuỗi trống')
        payload={'model':self.settings.embed_model,'input':text[:4500], 'truncate':True}
        with self._ollama_lock:
            result=http_json(self.settings.ollama_url+'/api/embed',payload,timeout=480)
        vectors=result.get('embeddings',[])
        if not vectors or not isinstance(vectors[0],list): raise ProviderError('Ollama không trả embedding')
        return vectors[0]
