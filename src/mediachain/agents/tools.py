"""Owner-scoped read-only media tools; frame writes remain inside a configured directory."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import Field

from mediachain.core.models import ExecutionContext, Modality, Model, RetrievalFilter, stable_id
from mediachain.modalities.audio.ffmpeg import extract_frame
from mediachain.runtime.client import MediaChain


class SearchArguments(Model):
    query: str = ""
    media_ids: list[str] | None = None
    start_time: float | None = Field(default=None, ge=0)
    end_time: float | None = Field(default=None, ge=0)
    limit: int = Field(default=5, ge=1, le=50)


class MediaTool:
    def __init__(
        self,
        name: str,
        chain: MediaChain,
        owner_id: str,
        output_dir: Path | None = None,
        media_ids: list[str] | None = None,
    ):
        self.name, self.chain, self.owner_id, self.output_dir = name, chain, owner_id, output_dir
        self.media_ids = set(media_ids) if media_ids is not None else None
        purpose = {
            "search_text": "Search indexed text, documents and PDFs",
            "search_audio": "Search speech transcripts from audio or video",
            "search_video": "Search visual descriptions from video frames",
            "search_timeline": "Search all evidence around timestamps",
            "get_transcript": "Read transcript segments in chronological order",
            "summarize_media": "Generate a grounded summary of the selected media",
            "extract_frame": "Extract one video frame at a timestamp",
        }[name]
        self.description = (
            purpose + ". Arguments: {query: string, media_ids?: string[], start_time?: seconds, "
            "end_time?: seconds, limit?: 1..50}. Omit media_ids to use the allowed selection."
        )

    async def invoke(self, arguments: dict[str, Any], context: ExecutionContext) -> Any:
        if context.owner_id != self.owner_id:
            raise PermissionError("Tool owner mismatch")
        args = SearchArguments.model_validate(arguments)
        assets = await self.chain.metadata.list_assets(self.owner_id)
        allowed = {a.id: a for a in assets}
        if self.media_ids is not None:
            allowed = {key: asset for key, asset in allowed.items() if key in self.media_ids}
        selected = args.media_ids if args.media_ids is not None else list(allowed)
        if any(i not in allowed for i in selected):
            raise KeyError("Unknown media")
        modality = {
            "search_text": Modality.TEXT,
            "search_audio": Modality.AUDIO,
            "search_video": Modality.VIDEO,
            "get_transcript": Modality.AUDIO,
        }.get(self.name)
        filters = RetrievalFilter(
            media_ids=selected,
            modalities=[modality] if modality else None,
            start_time=args.start_time,
            end_time=args.end_time,
        )
        if self.name == "extract_frame":
            if len(selected) != 1 or args.start_time is None or self.output_dir is None:
                raise ValueError(
                    "extract_frame requires one asset, time bounds and configured output directory"
                )
            asset = allowed[selected[0]]
            if asset.media_type != Modality.VIDEO or (
                asset.duration is not None and args.start_time > asset.duration
            ):
                raise ValueError("Invalid video timestamp")
            self.output_dir.mkdir(parents=True, exist_ok=True)
            path = self.output_dir / (stable_id(asset.id, args.start_time) + ".jpg")
            await extract_frame(Path(asset.source), args.start_time, path)
            return {"path": str(path), "media_id": asset.id, "timestamp": args.start_time}
        if self.name == "summarize_media":
            result = await self.chain.ask(
                args.query or "Summarize the available evidence",
                selected,
                owner_id=self.owner_id,
                filters=filters,
                context=context,
            )
            return result.model_dump(mode="json")
        if self.name in ("get_transcript", "search_timeline") and not args.query:
            docs = await self.chain.documents.list_documents(filters)
            return [
                d.model_dump(mode="json")
                for d in sorted(docs, key=lambda d: d.start_time or 0)[: args.limit]
            ]
        await self.chain._restore_vectors([allowed[i] for i in selected])
        return [
            r.model_dump(mode="json")
            for r in await self.chain.retriever.retrieve(args.query, filters, args.limit)
        ]


def media_tools(
    chain: MediaChain,
    owner_id: str = "local",
    output_dir: Path | None = None,
    media_ids: list[str] | None = None,
) -> list[MediaTool]:
    names = [
        "search_text",
        "search_audio",
        "search_video",
        "search_timeline",
        "get_transcript",
        "summarize_media",
    ]
    if output_dir is not None:
        names.append("extract_frame")
    return [MediaTool(name, chain, owner_id, output_dir, media_ids) for name in names]
