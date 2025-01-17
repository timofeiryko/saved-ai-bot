import orjson
import polars as pl
from datetime import datetime
from typing import Tuple, List, Dict
import os
from collections import deque


class TelegramChatParser:
    """Parser for Telegram chat history exported as JSON using Polars."""

    def __init__(self, max_messages: int = 50000):
        """Initialize the parser with necessary configurations.

        Parameters
        ----------
        max_messages : int, optional
            Maximum number of messages to retain, by default 50000
        """
        self.columns = [
            "msg_id",
            "sender",
            "sender_id",
            "reply_to_msg_id",
            "date",
            "date_unixtime",
            "msg_type",
            "msg_content",
            "forwarded_from",
            "action",
            "has_mention",
            "has_email",
            "has_phone",
            "has_hashtag",
            "is_bot_command",
        ]
        self.file_types = {
            "animation",
            "video_file",
            "video_message",
            "voice_message",
            "audio_file",
        }
        self.mention_types = {
            "mention",
            "mention_name",
        }
        self.max_messages = max_messages  # Set the maximum number of messages

    @staticmethod
    def timestamp() -> str:
        """Generate a string with the current timestamp.

        Returns
        -------
            str
                Current timestamp in '%Y-%m-%d_%H-%M-%S' format.
        """
        now = datetime.now()
        return now.strftime("%Y-%m-%d_%H-%M-%S")

    @staticmethod
    def debug(msg: str):
        """Simple debug function with runtime timestamp.

        Parameters
        ----------
            msg : str
                Developer text to be shown in the default output.
        """
        print(f"DEBUG | {TelegramChatParser.timestamp()} | {msg}")

    def process_message(self, message: Dict, chat_name: str) -> Dict:
        """Parse a single message from the chat.

        Parameters
        ----------
        message : dict
            A message object from the chat JSON.
        chat_name : str
            The name of the chat the message belongs to.

        Returns
        -------
        dict or None
            Parsed message as a dictionary, or None if not a valid message.
        """
        if message.get("type") != "message":
            return None

        msg_id = message.get("id", "")
        sender = message.get("from", "")
        sender_id = message.get("from_id", "")
        date = message.get("date", "")
        date_unixtime = message.get("date_unixtime", "")

        reply_to_msg_id = message.get("reply_to_message_id", "")
        action = message.get("action", "")
        forwarded_from = message.get("forwarded_from", "")

        has_mention = 0
        has_email = 0
        has_phone = 0
        has_hashtag = 0
        is_bot_command = 0

        msg_content = message.get("text", "")
        msg_type = "text"

        if "media_type" in message:
            msg_type = message["media_type"]
            if message["media_type"] == "sticker":
                msg_content = message.get("file", "?") if not message.get("sticker_emoji") else message.get("file", "?")
            else:
                msg_content = message.get("file", "?")
        elif "file" in message:
            msg_type = "file"
            msg_content = message["file"]

        if "photo" in message:
            msg_type = "photo"
            msg_content = message["photo"]
        elif "poll" in message:
            msg_type = "poll"
            msg_content = str(message["poll"].get("total_voters", 0))
        elif "location_information" in message:
            msg_type = "location"
            loc = message["location_information"]
            msg_content = f"{loc.get('latitude', '')},{loc.get('longitude', '')}"

        if isinstance(msg_content, list):
            txt_content = ""
            for part in msg_content:
                if isinstance(part, str):
                    txt_content += part
                elif isinstance(part, dict):
                    part_type = part.get("type", "")
                    if part_type == "link":
                        msg_type = "link"
                    elif part_type in self.mention_types:
                        has_mention = 1
                    elif part_type == "email":
                        has_email = 1
                    elif part_type == "phone":
                        has_phone = 1
                    elif part_type == "hashtag":
                        has_hashtag = 1
                    elif part_type == "bot_command":
                        is_bot_command = 1
                    txt_content += part.get("text", "")
            msg_content = txt_content

        msg_content = str(msg_content).replace("\n", " ")

        parsed_row = {
            "msg_id": msg_id,
            "sender": sender,
            "sender_id": sender_id,
            "reply_to_msg_id": reply_to_msg_id,
            "date": date,
            "date_unixtime": date_unixtime,
            "msg_type": msg_type,
            "msg_content": msg_content,
            "forwarded_from": forwarded_from,
            "action": action,
            "has_mention": has_mention,
            "has_email": has_email,
            "has_phone": has_phone,
            "has_hashtag": has_hashtag,
            "is_bot_command": is_bot_command,
            "chat_name": chat_name,  # Include chat name
        }

        return parsed_row

    def process_chat(self, chat_data: Dict, chats_deque: deque):
        """Process a single chat from the exported data.

        Parameters
        ----------
        chat_data : dict
            A chat object from the exported JSON.
        chats_deque : deque
            Deque to store the parsed messages with a fixed maximum length.

        Returns
        -------
        None
        """
        chat_name = chat_data.get("name", "Unknown Chat")
        messages = chat_data.get("messages", [])

        for message in messages:
            parsed_row = self.process_message(message, chat_name)
            if parsed_row:
                chats_deque.append(parsed_row)

    def process(self, file_path: str) -> Tuple[pl.DataFrame, str]:
        """Process the chat history JSON file.

        Parameters
        ----------
        file_path : str
            Path to the exported 'result.json' file.

        Returns
        -------
        Tuple[pl.DataFrame, List[str]]
            DataFrame of messages and the list of involved chat names.
        """
        try:
            with open(file_path, "r", encoding="utf-8") as file:
                jdata = orjson.loads(file.read())
        except Exception as e:
            self.debug(f"Failed to load JSON file: {e}")
            raise ValueError("Invalid JSON file or format.")

        # Initialize a deque with a fixed maximum length to store the last 50,000 messages
        chats_deque = deque(maxlen=self.max_messages)
        chat_names_set = set()

        # Handle different possible structures
        if "chats" in jdata and "list" in jdata["chats"]:
            chat_list = jdata["chats"]["list"]
            for chat in chat_list:
                self.process_chat(chat, chats_deque)
                chat_name = chat.get("name", "Unknown Chat")
                chat_names_set.add(chat_name)
        elif "left_chats" in jdata and "list" in jdata["left_chats"]:
            chat_list = jdata["left_chats"]["list"]
            for chat in chat_list:
                self.process_chat(chat, chats_deque)
                chat_name = chat.get("name", "Unknown Chat")
                chat_names_set.add(chat_name)
        elif "name" in jdata and "messages" in jdata:
            self.process_chat(jdata, chats_deque)
            chat_name = jdata.get("name", "Unknown Chat")
            chat_names_set.add(chat_name)
        else:
            self.debug("Unrecognized JSON structure.")
            raise ValueError("Invalid chat history JSON format.")

        if not chats_deque:
            self.debug("No messages found in the chat history.")
            raise ValueError("No messages found in the chat history.")

        # Convert the deque to a list
        chats = list(chats_deque)

        # Create a Polars DataFrame from the list of dictionaries
        try:
            df = pl.DataFrame(chats, schema=self.columns)
        except Exception as e:
            self.debug(f"Failed to create DataFrame: {e}")
            raise ValueError("Failed to create DataFrame from processed messages.")

        # Optionally, sort the DataFrame by date_unixtime to ensure chronological order
        try:
            df = df.sort("date_unixtime")
        except Exception as e:
            self.debug(f"Failed to sort DataFrame: {e}")
            # If sorting fails, proceed without sorting

        # Collect unique chat names
        chat_names = list(chat_names_set)

        return df, chat_names[0]

def parse_telegram_chat(file_path: str, max_messages: int = 50000) -> Tuple[pl.DataFrame, str]:
    """Parse a Telegram chat history JSON file and return a Polars DataFrame and chat names.

    Parameters
    ----------
    file_path : str
        Path to the exported 'result.json' file.
    max_messages : int, optional
        Maximum number of messages to retain, by default 50000.

    Returns
    -------
    Tuple[pl.DataFrame, List[str]]
        DataFrame of messages and the list of involved chat names.
    """
    parser = TelegramChatParser(max_messages=max_messages)
    df, chat_name = parser.process(file_path)

    os.remove(file_path)  # Remove the JSON file after processing

    return df, chat_name