from pydantic import confloat, constr
from enum import Enum

from pydantic import BaseModel

ProbabilityType = confloat(ge=0.0, le=1.0)
LanguageType = constr(regex=r"^(fr|en)$")


class TranscriptorSource(str, Enum):
    whisper = "whisper"
    whisperx = "whisperx"


class TimecodedLine(BaseModel):
    tc: str
    txt: str
