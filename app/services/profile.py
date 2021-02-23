import asyncio
import logging

import instaloader
import sqlalchemy
import sqlalchemy as sa
from databases import Database
from sqlalchemy.dialects.postgresql import insert

from services import schema
from services.entities import Profile, ProfileListResult

logger = logging.getLogger(__name__)


class ProfileService:
    def __init__(self, connection: sqlalchemy.engine.Connection, database: Database):
        self.connection = connection
        self.database = database
        self.instaloader_context = instaloader.InstaloaderContext()

    async def upsert(self, username: str):
        """Create or update a profile.

        :param username: username of the profile to create or update
        """

        # fetch profile
        loop = asyncio.get_running_loop()
        try:
            func = instaloader.Profile.from_username
            profile = await loop.run_in_executor(None, func, self.instaloader_context, username)
        except instaloader.ProfileNotExistsException:
            logger.warning(f'Profile does not exist: {username}')
            return

        # upsert profile
        values = {
            'username': profile.username,
            'full_name': profile.full_name,
            'biography': profile.biography,
        }
        updates = values.copy()
        updates.pop('username')
        statement = insert(schema.profiles, bind=self.connection.engine) \
            .values(**values) \
            .on_conflict_do_update(index_elements=[schema.profiles.c.username], set_=updates)
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self.connection.execute, statement)

        logger.info(f'Created Profile: {username}')

    async def exists(self, username: str) -> bool:
        """Check if a profile exists.

        :param username: username of the profile to check
        :return: if the profile exists
        """

        statement = schema.profiles.select().where(schema.profiles.c.username == username)
        exists_statement = sa.select([sa.exists(statement)])

        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, self.connection.execute, exists_statement)
        return result.scalar()

    async def list(self, offset: int = 0, limit: int = 100) -> ProfileListResult:
        """List profiles.

        :param offset: the number of profiles to skip
        :param limit: the number of profiles to fetch
        :return: the list query result
        """

        statement = schema.profiles.select(offset=offset, limit=limit)
        profiles = [Profile(**profile) for profile in await self.database.fetch_all(query=statement)]

        statement = sa.select([sa.func.count()]).select_from(schema.profiles)
        count = await self.database.fetch_val(query=statement)

        return ProfileListResult(profiles=profiles, limit=limit, offset=offset, count=count)
