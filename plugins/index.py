# Don't Remove Credit @VJ_Botz
# Subscribe YouTube Channel For Amazing Bot @Tech_VJ
# Ask Doubt on Telegram @KingVJ01

import logging
import re
import asyncio
from utils import temp
from info import ADMINS
from pyrogram import Client, filters, enums
from pyrogram.errors import FloodWait
from pyrogram.errors.exceptions.bad_request_400 import ChannelInvalid, ChatAdminRequired, UsernameInvalid, UsernameNotModified
from info import INDEX_REQ_CHANNEL as LOG_CHANNEL
from database.ia_filterdb import save_file
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# Logger setup
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

lock = asyncio.Lock()

@Client.on_callback_query(filters.regex(r'^index'))
async def index_files(bot, query):
    if query.data.startswith('index_cancel'):
        temp.CANCEL = True
        return await query.answer("Cancelling Indexing")
    
    _, action, chat, lst_msg_id, from_user = query.data.split("#")
    
    if action == 'reject':
        await query.message.delete()
        await bot.send_message(
            int(from_user),
            f'Your submission for indexing {chat} has been declined by our moderators.',
            reply_to_message_id=int(lst_msg_id)
        )
        return

    if lock.locked():
        return await query.answer('Wait until previous process completes.', show_alert=True)
    
    msg = query.message
    await query.answer('Processing...⏳', show_alert=True)

    if int(from_user) not in ADMINS:
        await bot.send_message(
            int(from_user),
            f'Your submission for indexing {chat} has been accepted by our moderators and will be added soon.',
            reply_to_message_id=int(lst_msg_id)
        )
    
    await msg.edit(
        "Starting Indexing",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton('Cancel', callback_data='index_cancel')]]
        )
    )
    
    try:
        chat = int(chat)
    except ValueError:
        pass

    await index_files_to_db(int(lst_msg_id), chat, msg, bot)


@Client.on_message(filters.private & filters.command('index'))
async def send_for_index(bot, message):
    vj = await bot.ask(
        message.chat.id,
        "**Now send me your channel's last post link or forward the last message from your index channel.**\n\n"
        "You can set a skip number using `/setskip yourskipnumber`."
    )

    if vj.forward_from_chat and vj.forward_from_chat.type == enums.ChatType.CHANNEL:
        last_msg_id = vj.forward_from_message_id
        chat_id = vj.forward_from_chat.username or vj.forward_from_chat.id
    elif vj.text:
        regex = re.compile(r"(https://)?(t\.me/|telegram\.me/|telegram\.dog/)(c/)?(\d+|[a-zA-Z_0-9]+)/(\d+)$")
        match = regex.match(vj.text)
        if not match:
            return await vj.reply('Invalid link\n\nTry again with /index.')
        chat_id = match.group(4)
        last_msg_id = int(match.group(5))
        if chat_id.isnumeric():
            chat_id = int("-100" + chat_id)
    else:
        return

    try:
        await bot.get_chat(chat_id)
    except ChannelInvalid:
        return await vj.reply('This may be a private channel or group. Make me an admin there to index the files.')
    except (UsernameInvalid, UsernameNotModified):
        return await vj.reply('Invalid link specified.')
    except Exception as e:
        logger.exception(e)
        return await vj.reply(f'Error: {e}')
    
    try:
        k = await bot.get_messages(chat_id, last_msg_id)
    except:
        return await message.reply('Make sure I am an admin in the channel if it is private.')

    if k.empty:
        return await message.reply('This may be a group, and I am not an admin of the group.')

    if message.from_user.id in ADMINS:
        buttons = [
            [InlineKeyboardButton('Yes', callback_data=f'index#accept#{chat_id}#{last_msg_id}#{message.from_user.id}')],
            [InlineKeyboardButton('Close', callback_data='close_data')]
        ]
        reply_markup = InlineKeyboardMarkup(buttons)
        return await message.reply(
            f'Do you want to index this channel/group?\n\n'
            f'Chat ID/Username: <code>{chat_id}</code>\nLast Message ID: <code>{last_msg_id}</code>',
            reply_markup=reply_markup
        )

    if isinstance(chat_id, int):
        try:
            link = (await bot.create_chat_invite_link(chat_id)).invite_link
        except ChatAdminRequired:
            return await message.reply('Make sure I am an admin in the chat with permission to invite users.')
    else:
        link = f"@{message.forward_from_chat.username}"

    buttons = [
        [InlineKeyboardButton('Accept Index', callback_data=f'index#accept#{chat_id}#{last_msg_id}#{message.from_user.id}')],
        [InlineKeyboardButton('Reject Index', callback_data=f'index#reject#{chat_id}#{message.id}#{message.from_user.id}')]
    ]
    reply_markup = InlineKeyboardMarkup(buttons)

    await bot.send_message(
        LOG_CHANNEL,
        f'#IndexRequest\n\nBy: {message.from_user.mention} (<code>{message.from_user.id}</code>)\n'
        f'Chat ID/Username: <code>{chat_id}</code>\nLast Message ID: <code>{last_msg_id}</code>\n'
        f'Invite Link: {link}',
        reply_markup=reply_markup
    )
    await message.reply('Thank you for the contribution. Wait for our moderators to verify the files.')


@Client.on_message(filters.command('setskip') & filters.user(ADMINS))
async def set_skip_number(bot, message):
    if ' ' in message.text:
        _, skip = message.text.split(" ")
        try:
            skip = int(skip)
        except ValueError:
            return await message.reply("Skip number should be an integer.")
        temp.CURRENT = skip
        await message.reply(f"Successfully set SKIP number to {skip}")
    else:
        await message.reply("Provide a skip number.")


async def index_files_to_db(lst_msg_id, chat, msg, bot):
    total_files = 0
    duplicate = 0
    errors = 0
    deleted = 0
    no_media = 0
    unsupported = 0

    async with lock:
        try:
            current = temp.CURRENT
            temp.CANCEL = False
            async for message in bot.iter_messages(chat, lst_msg_id, temp.CURRENT):
                if temp.CANCEL:
                    await msg.edit(
                        f"Indexing cancelled!\n\n"
                        f"Saved: <code>{total_files}</code>\n"
                        f"Duplicates: <code>{duplicate}</code>\n"
                        f"Deleted: <code>{deleted}</code>\n"
                        f"Non-Media: <code>{no_media + unsupported}</code> (Unsupported: {unsupported})\n"
                        f"Errors: <code>{errors}</code>"
                    )
                    break

                current += 1

                # Update progress every 30 messages
                if current % 30 == 0:
                    current_text = msg.text or msg.caption
                    new_text = (
                        f"Total messages fetched: <code>{current}</code>\n"
                        f"Total saved: <code>{total_files}</code>\n"
                        f"Duplicates: <code>{duplicate}</code>\n"
                        f"Deleted: <code>{deleted}</code>\n"
                        f"Non-Media: <code>{no_media + unsupported}</code> (Unsupported: {unsupported})\n"
                        f"Errors: <code>{errors}</code>"
                    )
                    if current_text != new_text:
                        await msg.edit_text(
                            text=new_text,
                            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('Cancel', callback_data='index_cancel')]])
                        )

                if message.empty:
                    deleted += 1
                    continue
                elif not message.media:
                    no_media += 1
                    continue
                elif message.media not in [enums.MessageMediaType.VIDEO, enums.MessageMediaType.AUDIO, enums.MessageMediaType.DOCUMENT]:
                    unsupported += 1
                    continue

                media = getattr(message, message.media.value, None)
                if not media:
                    unsupported += 1
                    continue

                media.file_type = message.media.value
                media.caption = message.caption
                success, result = await save_file(media)

                if success:
                    total_files += 1
                elif result == 0:
                    duplicate += 1
                elif result == 2:
                    errors += 1

        except Exception as e:
            logger.exception(e)
            await msg.edit(f'Error: {e}')
        else:
            await msg.edit(
                f"Indexing completed!\n\n"
                f"Saved: <code>{total_files}</code>\n"
                f"Duplicates: <code>{duplicate}</code>\n"
                f"Deleted: <code>{deleted}</code>\n"
                f"Non-Media: <code>{no_media + unsupported}</code> (Unsupported: {unsupported})\n"
                f"Errors: <code>{errors}</code>"
    )
        
