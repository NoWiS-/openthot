import os
from pathlib import Path

import structlog
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.encoders import jsonable_encoder

from stt.api import auth
from stt.config import get_settings
from stt.db import rw
from stt.db.database import DBUserBase, get_db
from stt.models.interview import Interview, InterviewCreate, InterviewUpdate
from stt.tasks.tasks import process_audio_task

logger = structlog.get_logger(__file__)
router = APIRouter(
    prefix="/interviews",
    tags=["interviews"],
)


@router.get(
    "/",
    response_model=list[Interview] | None,
    response_model_exclude={"transcript"},
    response_model_exclude_none=True,
)
async def list_interviews(
    db=Depends(get_db), current_user: DBUserBase = Depends(auth.current_active_user)
):
    """List all existing interviews."""
    return list(await rw.get_interviews(db, current_user))


@router.post("/", response_model=Interview)
async def create_interview(
    interview: InterviewCreate = Depends(),
    audio_file: UploadFile = File(description="The audio file of the interview."),
    db=Depends(get_db),
    current_user: DBUserBase = Depends(auth.current_active_user),
):
    """Create a new interview to be transcripted."""
    persistent_location = Path(get_settings().object_storage_path, audio_file.filename)
    os.makedirs(os.path.dirname(os.path.abspath(persistent_location)), exist_ok=True)
    await logger.adebug(
        "Intending to write audio file",
        persistent_location=persistent_location,
        interview=interview,
    )
    with open(persistent_location, "wb") as persistent_file:
        persistent_file.write(audio_file.file.read())
    await logger.adebug("Just wrote audio file.")
    new_interview = await rw.create_interview(
        db, user=current_user, interview=interview, audio_location=persistent_location
    )
    try:
        process_audio_task.delay(
            interview_id=new_interview.id, audio_location=new_interview.audio_location
        )
    except Exception:
        logger.exception("Could not launch task")
        await rw.delete_interview(
            db, user=current_user, interview_id=jsonable_encoder(new_interview)["id"]
        )
        raise  # TODO return correct error response model
    return new_interview


@router.delete("/{interview_id}")
async def delete_interview(
    interview_id: int,
    db=Depends(get_db),
    current_user: DBUserBase = Depends(auth.current_active_user),
):
    """Delete a specific interview."""
    await rw.delete_interview(db, current_user, interview_id)


@router.get("/{interview_id}", response_model=Interview)
async def get_interview(
    interview_id: int,
    db=Depends(get_db),
    current_user: DBUserBase = Depends(auth.current_active_user),
):
    """Get a specific interview."""
    interview = await rw.get_interview(db, current_user, interview_id)
    if interview:
        return interview
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail="Interview does not exist."
    )


@router.patch("/{interview_id}", response_model=Interview)
async def update_interview(
    interview_id: int,
    interview: InterviewUpdate,
    db=Depends(get_db),
    current_user: DBUserBase = Depends(auth.current_active_user),
):
    """Update a specific interview."""
    interview_target = await rw.get_interview(db, current_user, interview_id)
    if not interview_target:
        raise Exception
    new_interview = await rw.update_interview(
        db, interview_db=interview_target, interview_upd=interview
    )
    return new_interview