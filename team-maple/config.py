import os
import random
from typing import List, Optional, TYPE_CHECKING


from dotenv import load_dotenv
from hata.discord import Client, ChannelText
from hata.discord.parsers import EventDescriptor, _EventHandlerManager
from hata.ext.commands import setup_ext_commands, CommandProcesser
from hata.backend import KeepType, sleep

load_dotenv()


# When delaying, the least and most amount of seconds to wait to appear human
HUMAN_DELAY_RANGE = (1, 2)


# Required to make type checkers happy
if TYPE_CHECKING:
	class MapleClient(Client):
		command_processer: CommandProcesser
		commands: _EventHandlerManager
		events: EventDescriptor
		potato_channel: ChannelText

		def _init(self, potato_channel: ChannelText) -> 'MapleClient':
			...

		async def human_delay(self, channel: Optional[ChannelText] = ...) -> None:
			...
else:
	@KeepType(Client)
	class MapleClient:
		def _init(self, potato_channel):
			self.potato_channel = potato_channel
			return self

		async def human_delay(self, channel=None):
			if channel:
				await self.typing(channel)

			await sleep(random.uniform(*HUMAN_DELAY_RANGE))


def create_clients() -> None:
	"""Create all clients"""
	# TODO - implement error handling based on missing or invalid enviroment values
	client_ids = [int(token.strip()) for token in (os.getenv('CLIENT_IDS') or '').split(',') if token]
	client_tokens = [token.strip() for token in (os.getenv('CLIENT_TOKENS') or '').split(',') if token]
	potato_channels: List[ChannelText] = [
		ChannelText.precreate(int(id.strip()))
		for id in (os.getenv('POTATO_CHANNEL_IDS') or '').split(',')
		if id.strip()
	]

	for i, token in enumerate(client_tokens):
		client = MapleClient(token, client_id=client_ids[i])._init(potato_channels[i])
		# TODO - parameterize prefix
		setup_ext_commands(client, '.')
