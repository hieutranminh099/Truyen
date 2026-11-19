"""Voice profiles and focused revision plans for Vietnamese fiction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .style_analyzer import StyleFinding, analyze_style


@dataclass(frozen=True, slots=True)
class CharacterVoice:
    name: str
    register: str
    diction: str
    subtext: str = ""


@dataclass(frozen=True, slots=True)
class SituationVoice:
    situation: str
    guidance: str


@dataclass(frozen=True, slots=True)
class VoiceBible:
    pov: str
    sentence_rhythm: str = ""
    paragraph_rhythm: str = ""
    description: str = ""
    emotional_tone: str = ""
    interiority: str = ""
    dialogue_subtext: str = ""
    avoid_words: tuple[str, ...] = ()
    avoid_structures: tuple[str, ...] = ()
    character_voices: tuple[CharacterVoice, ...] = ()
    situational_voices: tuple[SituationVoice, ...] = ()

    def to_markdown(self) -> str:
        """Render a profile for the existing V4 Markdown voice field."""
        sections = [
            ("Điểm nhìn", self.pov),
            ("Nhịp câu", self.sentence_rhythm),
            ("Nhịp đoạn", self.paragraph_rhythm),
            ("Miêu tả", self.description),
            ("Sắc thái", self.emotional_tone),
            ("Nội tâm", self.interiority),
            ("Ẩn ý trong lời thoại", self.dialogue_subtext),
            ("Từ và cụm từ nên hạn chế", "\n".join(f"- {word}" for word in self.avoid_words)),
            ("Cách mở câu nên hạn chế", "\n".join(f"- {phrase}" for phrase in self.avoid_structures)),
            ("Giọng từng nhân vật", "\n".join(
                f"- **{voice.name}** — " + " ".join(filter(None, (voice.register, voice.diction, voice.subtext)))
                for voice in self.character_voices
            )),
            ("Giọng kể theo tình huống", "\n".join(
                f"- **{voice.situation}** — {voice.guidance}" for voice in self.situational_voices
            )),
        ]
        return "# Hồ sơ giọng văn\n\n" + "\n\n".join(
            f"## {name}\n\n{body.strip()}" for name, body in sections if body.strip()
        ) + "\n"


def plan_revision(
    text: str,
    bible: VoiceBible | None = None,
    *,
    dialogue_speakers: Mapping[int, str] | None = None,
    max_items: int = 8,
) -> tuple[StyleFinding, ...]:
    """Select the highest-priority suggestions without modifying the draft."""
    if max_items < 0:
        raise ValueError("max_items phải không âm")
    findings = analyze_style(
        text,
        avoid_words=bible.avoid_words if bible else (),
        avoid_structures=bible.avoid_structures if bible else (),
        dialogue_speakers=dialogue_speakers,
    )
    ordered = sorted(findings, key=lambda item: (item.priority, item.location.start, item.kind))
    return tuple(ordered[:max_items])
