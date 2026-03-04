from django.apps import AppConfig


class AccountsConfig(AppConfig):
    name = "apps.accounts"

    def ready(self) -> None:
        """Import signal handlers when the app is ready."""
        import apps.accounts.signals  # noqa: F401
