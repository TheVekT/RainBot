from abc import ABC, abstractmethod
from datetime import datetime

class AbstractPresenceRepository(ABC):
    """
    Abstract interface for persisting and managing user presence and account profiles.
    """

    @abstractmethod
    async def is_account_exist(self, account_id: int) -> bool:
        """
        Checks if an account exists in the cache or database.
        """
        pass

    @abstractmethod
    async def create_account(self, account_id: int, nickname: str, avatar_url: str, current_status: str) -> None:
        """
        Creates a new user profile in the database.
        """
        pass

    @abstractmethod
    async def update_account_status(self, account_id: int, current_status: str) -> None:
        """
        Updates only the real-time status field for a specific account.
        """
        pass

    @abstractmethod
    async def bulk_upsert_accounts(self, accounts: list[tuple]) -> None:
        """
        Performs a mass update/insert of account profiles for the 24-hour synchronization cycle.
        """
        pass

    @abstractmethod
    async def save_period(self, account_id: int, state: str, start_time: datetime, end_time: datetime) -> None:
        """
        Saves a continuous duration of user presence state log.
        """
        pass

    @abstractmethod
    async def clean_old_records(self, cutoff_date: datetime) -> None:
        """
        Removes historical presence logs older than the configured cutoff date.
        """
        pass

    @abstractmethod
    async def compress_records(self, since: datetime) -> None:
        """
        Merges adjacent historical entries with identical states to optimize storage.
        """
        pass