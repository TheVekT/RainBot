from abc import ABC, abstractmethod
from datetime import datetime


class AbstractPresenceRepository(ABC):
    """Interface for Discord account, channel and presence persistence."""

    @abstractmethod
    async def is_account_exist(self, account_id: int) -> bool:
        pass

    @abstractmethod
    async def create_account(self, account_id: int, username: str, nickname: str,
                             avatar_url: str, current_status: str) -> None:
        pass

    @abstractmethod
    async def update_account_status(self, account_id: int, current_status: str) -> None:
        pass

    @abstractmethod
    async def bulk_upsert_accounts(self, accounts: list[tuple]) -> None:
        pass

    @abstractmethod
    async def set_account_membership(self, account_id: int, is_member: bool) -> None:
        pass

    @abstractmethod
    async def reconcile_members(self, member_ids: list[int]) -> None:
        pass

    @abstractmethod
    async def is_channel_exist(self, channel_id: int) -> bool:
        pass

    @abstractmethod
    async def create_channel(self, channel_id: int, name: str, is_active: bool) -> None:
        pass

    @abstractmethod
    async def bulk_upsert_channels(self, channels: list[tuple]) -> None:
        pass

    @abstractmethod
    async def reconcile_channels(self, channel_ids: list[int]) -> None:
        pass

    @abstractmethod
    async def sync_channels(self, channels: list[tuple]) -> None:
        """Atomically upsert current channels and deactivate missing channels."""
        pass

    @abstractmethod
    async def save_period(self, account_id: int, state: str, start_time: datetime,
                          end_time: datetime, channel_id: int | None = None) -> None:
        pass

    @abstractmethod
    async def bulk_save_periods(self, periods: list[tuple]) -> None:
        """Atomically persist (account_id, state, start_time, end_time, channel_id) rows."""
        pass

    @abstractmethod
    async def clean_old_records(self, cutoff_date: datetime) -> None:
        pass

    @abstractmethod
    async def compress_records(self, since: datetime) -> None:
        pass
