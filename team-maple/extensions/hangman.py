import random
import re
from typing import Callable, Optional, Set, List, Any
from types import ModuleType


from hata.backend import sleep, Future
from hata.discord import (
	CLIENTS, BUILTIN_EMOJIS, KOKORO, Client, Message,
	Embed, EventWaitforBase, ReactionAddEvent, ChannelBase
)
from hata.ext.commands import utils, WaitAndContinue


from config import MapleClient


WORDBANK = [
	'Hello, World!',
	'Hata',
	'Tortoise',
	'Maple',
	'Discord',
	'Four',
	'Hail',
	'Wolf',
	'Cat',
	'Knock',
	'Hand',
	'Hang',
	'Halloween',
	'Quick',
	'Brown',
	'Fox',
	'Jump',
	'Lazy',
	'Dog',
]

RANDOM_LETTER_ORDER = 'ETAOINSHRDLUCMFWYPVBGKQJXZ'.lower()
BLANK_LETTER = '_'

START_HANGMAN_MESSAGE = 'Who wants to play hangman?'
START_HANGMAN_EMOJI_NAME = 'raised_hand'
START_HANGMAN_EMOJI = BUILTIN_EMOJIS[START_HANGMAN_EMOJI_NAME]

GUESS_WAIT_TIMEOUT = 30


def generate_hangman_embed(word: List[str], current: List[str], lives: int, won: Optional[bool], msg: str = ''):
	full_msg = '\n' + msg if msg else ''
	msg_and_word = '{}```\n{{}}\n```'.format(full_msg)
	embed = Embed('Hangman')
	if won is None:
		embed.description = '{} lives remaining...{}'.format(lives, msg_and_word.format(''.join(current)))
	elif won:
		embed.description = 'You won with {} lives remaining!{}'.format(lives, msg_and_word.format(''.join(current)))
	else:
		embed.description = 'You lost...{}'.format(msg_and_word.format(''.join(word)))
	return embed


active_games: Set[int] = set()


async def hangman(client: MapleClient, message: Message, guessing_word: str = ''):
	"""Start a game of hangman"""
	global active_games
	if message.id in active_games:
		return
	active_games.add(message.id)

	await client.typing(message.channel)

	# Prevent usage of BLANK_LETTER in word
	if guessing_word and BLANK_LETTER in guessing_word:
		await client.message_create(message.channel, 'Word cannot contain "{}"'.format(BLANK_LETTER))
		active_games.remove(message.id)
		return

	# Create prompt and wait for user to play
	hangman_msg = await client.message_create(message.channel, START_HANGMAN_MESSAGE)
	await client.reaction_add(hangman_msg, START_HANGMAN_EMOJI)
	try:
		event: ReactionAddEvent = await utils.wait_for_reaction(
			client,
			hangman_msg,
			lambda event: event.user.id != client.id and event.emoji.name == START_HANGMAN_EMOJI_NAME,
			GUESS_WAIT_TIMEOUT
		)
	except TimeoutError:
		await client.message_edit(hangman_msg, 'Guess nobody wants to play hangman...')
		return
	finally:
		active_games.remove(message.id)
		await client.reaction_delete_emoji(hangman_msg, START_HANGMAN_EMOJI)

	player_id = event.user.id
	random_word = guessing_word or random.choice(WORDBANK)
	word = list(random_word)
	current: List[str] = list(re.sub('[a-zA-Z]', BLANK_LETTER, random_word))
	lives = 6
	won: Optional[bool] = None

	await client.message_edit(hangman_msg, '', embed=generate_hangman_embed(word, current, lives, won))

	try:
		while won is None:
			# Wait for guess from user
			guess_msg = await utils.wait_for_message(
				client,
				message.channel,
				lambda msg: msg.author.id == player_id and len(msg.content) == 1 and msg.content[0].isalpha(),
				GUESS_WAIT_TIMEOUT
			)
			await client.typing(message.channel)
			letter: str = guess_msg.content[0].lower()
			await client.message_delete(guess_msg)

			response = ''
			if letter in current or letter.upper() in current:
				response = "You have already guessed `{}` ".format(letter)
			else:
				# Search for and reveal letters
				found = False
				for i, correct in enumerate(word):
					if correct.lower() == letter:
						current[i] = correct
						found = True
				if not found:
					lives -= 1

				if word == current:
					won = True
				elif lives == 0:
					won = False

			await client.message_edit(hangman_msg, embed=generate_hangman_embed(word, current, lives, won, response))
	except TimeoutError:
		won = False
		await client.message_edit(
			hangman_msg,
			embed=generate_hangman_embed(word, current, lives, won, 'The game was abandoned')
		)


def wait_for_message_edit(
	client: Client,
	channel: ChannelBase,
	check: Callable[[Message, Optional[dict]], Any],
	timeout: float
):
	future = Future(KOKORO)
	WaitAndContinue(future, check, channel, client.events.message_edit, timeout)
	return future


playing_games: Set[int] = set()


async def message_create(client: MapleClient, message: Message):
	# If already playing, not a hangman prompt, or is self, return
	if message.id in playing_games or message.content != START_HANGMAN_MESSAGE or message.author.id == client.id:
		return
	playing_games.add(message.id)

	# TODO - parameterize
	await sleep(random.uniform(2, 5))
	# If the offer has been retracted, return
	if START_HANGMAN_EMOJI not in message.reactions:
		return

	# React - accepting game offer
	await client.reaction_add(message, START_HANGMAN_EMOJI)

	# Wait for game message to be updated
	try:
		await wait_for_message_edit(client, message.channel, lambda msg, _: msg.id == message.id, GUESS_WAIT_TIMEOUT)
	except TimeoutError:
		return
	finally:
		playing_games.remove(message.id)

	random_letters = list(RANDOM_LETTER_ORDER)
	possible_words = [
		word.lower()
		for word in WORDBANK if
		len(word) == len(message.embeds[0].description.split('```')[1].strip())
	]
	tried: List[str] = []
	current: List[str] = []
	while True:
		embed = message.embeds[0]
		current = list(embed.description.split('```')[1].strip().lower())
		# Filter down possible words
		for word in possible_words[:]:
			# Remove word if a correct letter is not in the word at the correct position
			for i, letter in enumerate(current):
				if letter == BLANK_LETTER:
					continue
				if letter != word[i]:
					possible_words.remove(word)
					break

		# Get a count of the most popular letters between the possible words
		letter_counts = {}
		for word in possible_words:
			for letter in set(word.lower()):
				if letter in current or letter in tried:
					continue
				if letter not in letter_counts:
					letter_counts[letter] = 0
				letter_counts[letter] += 1
		popular = sorted(letter_counts.items(), key=lambda pair: pair[1], reverse=True)
		# Try to use most popular, otherwise use random letter in order of most popular
		if popular:
			trying = popular[0][0]
			random_letters.remove(trying)
		else:
			trying = random_letters.pop(0)
		tried.append(trying)

		await client.human_delay(message.channel)
		await client.message_create(message.channel, trying)
		await wait_for_message_edit(client, message.channel, lambda msg, _: msg.id == message.id, GUESS_WAIT_TIMEOUT)

		msg: str = message.embeds[0].description.lower().split('```')[0]
		# If the game is over, break free
		if any(keyword in msg for keyword in ('lost', 'won', 'over')):
			break


class MessageEditWaitfor(EventWaitforBase):
	__event_name__ = 'message_edit'


def setup(_: ModuleType):
	for client in CLIENTS:
		client.events(MessageEditWaitfor)
		client.events(message_create)
		client.commands(hangman)
