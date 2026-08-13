from django.apps import AppConfig


class LucidConfig(AppConfig):
    name = "lucid"

    def ready(self):
        # Importing the module is what registers its @register'd checks.
        from . import checks  # noqa: F401
