"""Approval gate for functions that spend money or write to production."""


class ApprovalRequired(SystemExit):
    """Refusal to spend or write without approval.

    A ``SystemExit`` subclass, so ``except Exception`` retry loops cannot swallow it.
    """

    def __init__(self, action: str):
        super().__init__(f"Refused: {action} needs approval. Pass --approved or approved=True.")
        self.action = action


def require_approval(action: str, approved: bool) -> None:
    """Raise ``ApprovalRequired`` unless ``approved`` is true. Call before any side effect."""
    if not approved:
        raise ApprovalRequired(action)
