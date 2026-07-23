from __future__ import annotations

import logging

from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters

from .config import ConfigurationError, Settings
from .handlers import BotHandlers
from .storage import Storage
from .trello_client import TrelloClient, TrelloError

logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)


def main() -> None:
    try: settings = Settings.from_env()
    except ConfigurationError as exc: raise SystemExit(f"Ошибка конфигурации: {exc}") from exc
    storage = Storage(settings.database_path); trello = TrelloClient(settings.trello_key, settings.trello_token, settings.trello_list_id)
    handlers = BotHandlers(settings, storage, trello)

    async def post_init(application: Application) -> None:
        await storage.initialize(settings.admin_telegram_user_id, settings.legacy_allowed_user_ids)
        try: await trello.check_ready(); logger.info("application_started trello_ready=true")
        except TrelloError as exc: logger.error("startup_trello_check_failed error_class=%s reason=%s", type(exc).__name__, exc)

    async def post_shutdown(application: Application) -> None: await trello.close()
    app = Application.builder().token(settings.telegram_token).post_init(post_init).post_shutdown(post_shutdown).build()
    for command, callback in (("start", handlers.start), ("help", handlers.help), ("cancel", handlers.cancel), ("new", handlers.new), ("status", handlers.status), ("check_trello", handlers.check_trello), ("admin", handlers.admin), ("myid", handlers.myid)):
        app.add_handler(CommandHandler(command, callback))
    app.add_handler(CallbackQueryHandler(handlers.callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.text))
    app.run_polling()


if __name__ == "__main__": main()
