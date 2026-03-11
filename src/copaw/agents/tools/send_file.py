# -*- coding: utf-8 -*-
# flake8: noqa: E501
# pylint: disable=line-too-long,too-many-return-statements
import os
import mimetypes
from pathlib import Path

from agentscope.tool import ToolResponse
from agentscope.message import (
    TextBlock,
    ImageBlock,
    AudioBlock,
    VideoBlock,
)

from ...app.user_scope import (
    get_current_user_id,
    get_user_root,
    get_user_workspace_dir,
)
from ...constant import WORKING_DIR, get_copaw_base_url
from ..schema import FileBlock


def _auto_as_type(mt: str) -> str:
    if mt.startswith("image/"):
        return "image"
    if mt.startswith("audio/"):
        return "audio"
    if mt.startswith("video/"):
        return "video"
    return "file"


async def send_file_to_user(
    file_path: str,
) -> ToolResponse:
    """Send a file to the user.

    Args:
        file_path (`str`):
            Path to the file to send.

    Returns:
        `ToolResponse`:
            The tool response containing the file or an error message.
    """

    if not os.path.exists(file_path):
        return ToolResponse(
            content=[
                TextBlock(
                    type="text",
                    text=f"Error: The file {file_path} does not exist.",
                ),
            ],
        )

    if not os.path.isfile(file_path):
        return ToolResponse(
            content=[
                TextBlock(
                    type="text",
                    text=f"Error: The path {file_path} is not a file.",
                ),
            ],
        )

    # Detect MIME type
    mime_type, _ = mimetypes.guess_type(file_path)
    if mime_type is None:
        # Default to application/octet-stream for unknown types
        mime_type = "application/octet-stream"
    as_type = _auto_as_type(mime_type)

    try:
        # text
        if as_type == "text":
            with open(file_path, "r", encoding="utf-8") as file:
                return ToolResponse(
                    content=[TextBlock(type="text", text=file.read())],
                )

        # Generate URL: use HTTP URL for files in WORKING_DIR, otherwise file://
        absolute_path = os.path.abspath(file_path)
        resolved_path = Path(absolute_path).resolve()

        current_user_id = get_current_user_id()
        user_workspace = get_user_workspace_dir(current_user_id).resolve()
        user_root = get_user_root(current_user_id).resolve()
        # Check if file is within current user's workspace
        if str(resolved_path).startswith(str(user_workspace)):
            # Generate HTTP URL for user workspace file.
            relative_path = resolved_path.relative_to(user_workspace)
            relative_url = (
                f"/api/workspace/file/u/{current_user_id}/{relative_path.as_posix()}"
            )
            # Use full URL if COPAW_BASE_URL is set (read at call time
            # to pick up Console-configured env vars)
            base_url = get_copaw_base_url()
            file_url = (
                f"{base_url}{relative_url}" if base_url else relative_url
            )
        elif str(resolved_path).startswith(str(user_root)):
            # Generate HTTP URL for files under current user root.
            relative_path = resolved_path.relative_to(user_root)
            relative_url = (
                f"/api/workspace/file/u/{current_user_id}/{relative_path.as_posix()}"
            )
            base_url = get_copaw_base_url()
            file_url = (
                f"{base_url}{relative_url}" if base_url else relative_url
            )
        elif str(resolved_path).startswith(str(WORKING_DIR)):
            # Backward-compatible fallback for legacy paths under WORKING_DIR.
            relative_path = resolved_path.relative_to(WORKING_DIR)
            relative_url = (
                f"/api/workspace/file/u/{current_user_id}/{relative_path.as_posix()}"
            )
            base_url = get_copaw_base_url()
            file_url = (
                f"{base_url}{relative_url}" if base_url else relative_url
            )
        else:
            # Use file:// URL for local files outside WORKING_DIR
            file_url = f"file://{absolute_path}"
            relative_url = file_url  # For non-WORKING_DIR files, use full path
        source = {"type": "url", "url": relative_url}

        if as_type == "image":
            return ToolResponse(
                content=[
                    ImageBlock(type="image", source=source),
                    TextBlock(type="text", text=f"[IMPORTANT] 请将以下链接包含在你的回复中，让用户可以直接点击：\n{file_url}"),
                ],
            )
        if as_type == "audio":
            return ToolResponse(
                content=[
                    AudioBlock(type="audio", source=source),
                    TextBlock(type="text", text=f"[IMPORTANT] 请将以下链接包含在你的回复中，让用户可以直接点击：\n{file_url}"),
                ],
            )
        if as_type == "video":
            return ToolResponse(
                content=[
                    VideoBlock(type="video", source=source),
                    TextBlock(type="text", text=f"[IMPORTANT] 请将以下链接包含在你的回复中，让用户可以直接点击：\n{file_url}"),
                ],
            )

        # For HTML files, return a clickable link instead of file download
        if mime_type == "text/html":
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=f"[IMPORTANT] 请将以下链接包含在你的回复中，让用户可以直接点击：\n{file_url}",
                    ),
                ],
            )

        return ToolResponse(
            content=[
                FileBlock(
                    type="file",
                    source=source,
                    filename=os.path.basename(file_path),
                ),
                TextBlock(type="text", text=f"[IMPORTANT] 请将以下链接包含在你的回复中，让用户可以直接点击：\n{file_url}"),
            ],
        )

    except Exception as e:
        return ToolResponse(
            content=[
                TextBlock(
                    type="text",
                    text=f"Error: Send file failed due to \n{e}",
                ),
            ],
        )
