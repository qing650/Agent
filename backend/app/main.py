from __future__ import annotations

import argparse
import logging
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .agents.chat.agent import ChatAgent
from .agents.rag.agent import RAGAgent
from .api.routers import aiops, chat, fashion, file, health, novel
from .core.llm import ChatLLM
from .storage.config import MemoryConfig
from .storage.manager import MemoryManager

logger = logging.getLogger(__name__)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


load_dotenv(_project_root() / ".env")


def create_app() -> FastAPI:
    app = FastAPI(title="MyAgent API", version="1.0.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router, prefix="/api", tags=["health"])
    app.include_router(chat.router, prefix="/api", tags=["chat"])
    app.include_router(fashion.router, prefix="/api", tags=["fashion"])
    app.include_router(file.router, prefix="/api", tags=["file"])
    app.include_router(aiops.router, prefix="/api", tags=["aiops"])
    app.include_router(novel.router, prefix="/api", tags=["novel"])

    static_dir = _project_root() / "static"
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    def serve_static_page(filename: str) -> FileResponse:
        return FileResponse(static_dir / filename)

    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return serve_static_page("index.html")

    @app.get("/chat", include_in_schema=False)
    async def chat_page() -> FileResponse:
        return serve_static_page("chat.html")

    @app.get("/novel", include_in_schema=False)
    async def novel_page() -> FileResponse:
        return serve_static_page("novel.html")

    @app.get("/fashion", include_in_schema=False)
    async def fashion_page() -> FileResponse:
        return serve_static_page("fashion.html")

    @app.get("/agents/chat", include_in_schema=False)
    async def chat_agent_page() -> FileResponse:
        return serve_static_page("chat.html")

    @app.get("/agents/novel", include_in_schema=False)
    async def novel_agent_page() -> FileResponse:
        return serve_static_page("novel.html")

    return app


app = create_app()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="MyAgent: RAG Agent + Chat Agent")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest = subparsers.add_parser("ingest", help="Ingest files or folders into the knowledge base")
    ingest.add_argument("paths", nargs="+", help="Files or folders to index")
    ingest.add_argument("--user-id", default=None, help="User id for private knowledge")
    ingest.add_argument("--private", action="store_true", help="Store indexed files as private knowledge")
    ingest.add_argument("--no-recursive", action="store_true", help="Do not walk folders recursively")

    search = subparsers.add_parser("search", help="Search the knowledge base")
    search.add_argument("query", help="Search query")
    search.add_argument("--user-id", default=None, help="User id")
    search.add_argument("--limit", type=int, default=5, help="Maximum results")

    chat_parser = subparsers.add_parser("chat", help="Ask the chat agent a question")
    chat_parser.add_argument("question", help="Question")
    chat_parser.add_argument("--session-id", default="default", help="Session id")
    chat_parser.add_argument("--user-id", default=None, help="User id")
    chat_parser.add_argument("--top-k", type=int, default=4, help="Knowledge snippets to retrieve")

    shell = subparsers.add_parser("shell", help="Interactive chat shell")
    shell.add_argument("--session-id", default="default", help="Session id")
    shell.add_argument("--user-id", default=None, help="User id")

    subparsers.add_parser("stats", help="Show workspace stats")

    serve = subparsers.add_parser("serve", help="Start the FastAPI web server")
    serve.add_argument("--host", default="127.0.0.1", help="Bind host")
    serve.add_argument("--port", type=int, default=8000, help="Bind port")
    serve.add_argument("--reload", action="store_true", help="Enable auto reload")
    return parser


def cmd_ingest(args: argparse.Namespace, rag_agent: RAGAgent) -> int:
    results = rag_agent.ingest(
        paths=args.paths,
        user_id=args.user_id,
        private=args.private,
        recursive=not args.no_recursive,
    )
    for result in results:
        if result.status == "indexed":
            print(f"[indexed] {result.path} ({result.chunks} chunks)")
        else:
            print(f"[failed] {result.path}: {result.error}")
    return 0


def cmd_search(args: argparse.Namespace, rag_agent: RAGAgent) -> int:
    results = rag_agent.search(query=args.query, user_id=args.user_id, limit=args.limit)
    if not results:
        print("No results.")
        return 0
    for index, result in enumerate(results, start=1):
        print(f"[{index}] {result.citation} score={result.score:.3f}")
        print(result.snippet)
        print()
    return 0


def cmd_chat(args: argparse.Namespace, chat_agent: ChatAgent) -> int:
    response = chat_agent.chat(
        question=args.question,
        session_id=args.session_id,
        user_id=args.user_id,
        top_k=args.top_k,
    )
    print(response.answer)
    if response.remembered:
        print("\nRemembered:")
        for item in response.remembered:
            print(f"- {item}")
    return 0


def cmd_shell(args: argparse.Namespace, rag_agent: RAGAgent, chat_agent: ChatAgent) -> int:
    print("MyAgent interactive shell")
    print("Commands:")
    print(":ingest <path>")
    print(":search <query>")
    print(":memory <query>")
    print(":exit")

    while True:
        try:
            raw = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not raw:
            continue
        if raw in {":exit", "exit", "quit"}:
            break
        if raw.startswith(":ingest "):
            target = raw[len(":ingest ") :].strip()
            results = rag_agent.ingest([target], user_id=args.user_id, private=False, recursive=True)
            for result in results:
                if result.status == "indexed":
                    print(f"[indexed] {result.path} ({result.chunks} chunks)")
                else:
                    print(f"[failed] {result.path}: {result.error}")
            continue
        if raw.startswith(":search "):
            query = raw[len(":search ") :].strip()
            results = rag_agent.search(query=query, user_id=args.user_id, limit=5)
            for index, result in enumerate(results, start=1):
                print(f"[{index}] {result.citation} score={result.score:.3f}")
                print(result.snippet)
            continue
        if raw.startswith(":memory "):
            query = raw[len(":memory ") :].strip()
            results = chat_agent.memory_manager.search_memory(
                query=query,
                user_id=args.user_id or chat_agent.config.default_user_id,
                limit=5,
            )
            for index, result in enumerate(results, start=1):
                print(f"[{index}] {result.citation} score={result.score:.3f}")
                print(result.snippet)
            continue
        response = chat_agent.chat(
            question=raw,
            session_id=args.session_id,
            user_id=args.user_id,
            top_k=4,
        )
        print(response.answer)
    return 0


def cmd_stats(memory_manager: MemoryManager) -> int:
    stats = memory_manager.get_stats()
    print(f"Workspace: {stats['workspace']}")
    print(f"Indexed files: {stats['files']}")
    print(f"Indexed chunks: {stats['chunks']}")
    if stats["documents"]:
        print("Documents:")
        for item in stats["documents"]:
            print(f"- {item}")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    try:
        import uvicorn
    except ImportError as exc:
        raise SystemExit("uvicorn is not installed. Run: py -3.12 -m pip install -r requirements.txt") from exc

    uvicorn.run(
        "backend.app.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        app_dir=str(_project_root()),
    )
    return 0


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "serve":
        return cmd_serve(args)

    config = MemoryConfig(project_root=_project_root())
    shared_memory_manager = MemoryManager(config=config)
    rag_agent = RAGAgent(config=config, memory_manager=shared_memory_manager)
    llm = ChatLLM()
    logger.info("LLM initialized: available=%s, model=%s", llm.available, llm.model)
    chat_agent = ChatAgent(config=config, memory_manager=shared_memory_manager, llm=llm)
    try:
        if args.command == "ingest":
            return cmd_ingest(args, rag_agent)
        if args.command == "search":
            return cmd_search(args, rag_agent)
        if args.command == "chat":
            return cmd_chat(args, chat_agent)
        if args.command == "shell":
            return cmd_shell(args, rag_agent, chat_agent)
        if args.command == "stats":
            return cmd_stats(shared_memory_manager)
        return 0
    finally:
        shared_memory_manager.close()


if __name__ == "__main__":
    raise SystemExit(main())
