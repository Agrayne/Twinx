import feedparser
from datetime import datetime
import pytz
from urllib.parse import urlparse
import discord
import asyncpg
import os
import hashlib
import logging
from dotenv import load_dotenv

load_dotenv()

# Variables

DB_USER = os.getenv('DB_USER')
DB_PASS = os.getenv('DB_PASS')
DB_NAME = os.getenv('DB_NAME')
BOT_TOKEN = os.getenv('BOT_TOKEN')

UPDATE_INTERVAL = os.getenv('UPDATE_INTERVAL')


#Setting up loggers

db_logger = logging.getLogger('Twinx DB')
db_logger.setLevel(logging.DEBUG)
db_console_handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(message)s')
db_console_handler.setFormatter(formatter)
db_logger.addHandler(db_console_handler)

info_logger = logging.getLogger('DB Events')
info_logger.setLevel(logging.DEBUG)
info_console_handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - Twinx DB - │ INFO:  %(message)s')
info_console_handler.setFormatter(formatter)
info_logger.addHandler(info_console_handler)

logger = logging.getLogger('Twinx')
logger.setLevel(logging.INFO)
console_handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)


# Secondary Functions

async def create_connection():
    try:
        conn = await asyncpg.connect(
            host='postgres',
            port=5432,
            user=DB_USER,
            password=DB_PASS,
            database=DB_NAME
        )
        db_logger.debug("┌ Connection to Database Successful")
        return conn
    except Exception as e:
        db_logger.error(f"Error connecting to the database: {e}")
        return None
    

async def close_connection(conn):
    if conn:
        await conn.close()
        db_logger.debug('└ Disconnected from the Database Successfully')


def create_timestamp(pubTime):
    pubTime = pytz.timezone('GMT').localize(datetime.strptime(pubTime, "%a, %d %b %Y %H:%M:%S %Z"))
    pubTime = round(pubTime.timestamp())
    return pubTime


def replace_link(link):
    link = urlparse(link)
    link = link._replace(netloc="vxtwitter.com").geturl()
    return link


def generate_message(name, feed_item):
    link = replace_link(feed_item.link)
    pubTime = create_timestamp(feed_item.published)

    if feed_item.title.startswith("RT by "):
        message = f"``{name.split()[-1]}`` retweeted ``{feed_item.author}``\n{link}"
    elif feed_item.title.startswith("R to "):
        message = f"``{name.split()[-1]}`` replied to ``{feed_item.title.split()[2][:-1]}`` on <t:{pubTime}>\n{link}"
    else:
        message = f"``{name}`` tweeted on <t:{pubTime}>\n{link}"
    return message


def get_username(title):
    return title.split()[-1][1:]


def create_hash(feed_dict):
    return hashlib.sha256((feed_dict.published + feed_dict.link).encode('utf-8')).hexdigest()


async def create_webhook(channel):
    webhook = await channel.create_webhook(name='Twinx')
    info_logger.debug(f'New webhook created for {channel.guild.name} in #{channel.name}')
    webhook_id = webhook.id
    webhook_token = webhook.token
    return (webhook_id, webhook_token)


# Database Query Functions

async def fetch_webhook_details(conn, channel_id):
    result = await conn.fetch('SELECT "webhookId", "webhookToken" FROM channels WHERE "channelId" = $1', channel_id)
    return result


async def fetch_subbed_webhook_details(conn, username):
    result = await conn.fetch('SELECT "webhookId", "webhookToken", channels."channelId" FROM subs JOIN channels ON subs."channelId" = channels."channelId" where subs."username" = ($1)', username)
    return result


async def fetch_guild_lists(conn):
    result = await conn.fetch('SELECT "guildId" FROM guilds') 
    return result


async def fetch_user_lists(conn):
    result = await conn.fetch('SELECT "username" FROM twitterUsers') 
    return result


async def fetch_user_hash_lists(conn):
    result = await conn.fetch('SELECT "username", "hash" FROM twitterUsers') 
    return result


async def fetch_subscribed_users(conn):
    result = await conn.fetch('SELECT DISTINCT "username" FROM subs')
    return result


async def fetch_subbed_users_by_channel(channel_id):
    conn = await create_connection()
    result = await conn.fetch('SELECT DISTINCT "username" FROM subs where "channelId" = $1', channel_id)
    await close_connection(conn)
    users = [user[0] for user in result]
    return users


async def update_webhook(channel):
    webhook = await channel.create_webhook(name='Twinx')
    webhook_id = webhook.id
    webhook_token = webhook.token

    conn = await create_connection()
    try:
        await conn.execute('UPDATE channels SET "webhookId" = $1, "webhookToken" = $2 WHERE "channelId" = $3', webhook_id, webhook_token, channel.id)
        info_logger.debug(f"Old webhook replaced by a new one for guild '{channel.guild.name}' in #{channel.name}")
    except Exception as e:
        db_logger.error(f"Error executing database query: {e}")
        
    await close_connection(conn)

    return (webhook_id, webhook_token)


async def update_hash(username, new_hash, conn):
    try:
        await conn.execute('UPDATE twitterUsers SET "hash" = $1 WHERE "username" = $2', new_hash, username)
        info_logger.debug(f'Hash updated for @{username}')
    except Exception as e:
        db_logger.error(f"Error executing database query: {e}")


async def username_in_db(new_user, conn):

    usernames = await conn.fetch('SELECT "username" FROM twitterUsers') 

    for username in usernames:
        if new_user == username[0]:
            return True
    return False


async def guild_in_db(new_guild_id, conn):

    guilds = await conn.fetch('SELECT "guildId" FROM guilds') 

    for guild_id in guilds:
        if new_guild_id == guild_id[0]:
            return True
    return False


async def channel_in_db(new_channel_id, conn):

    channels = await conn.fetch('SELECT "channelId" FROM channels') 

    for channel_id in channels:
        if new_channel_id == channel_id[0]:
            return True
    return False


async def sub_in_db(username, channel_id, conn):

    subs = await conn.fetch('SELECT "username", "channelId" FROM subs')

    for sub in subs:
        if (username, channel_id) == sub:
            return True
    return False


async def channel_in_sub(channel_id, conn):            # Redundant, but will keep this for now

    channels = await conn.fetch('SELECT "channelId" FROM subs')

    for channel in channels:
        if channel_id == channel[0]:
            return True
    return False


async def add_user(username, hash_code, conn):

    try:
        await conn.execute('INSERT INTO twitterUsers VALUES ($1, $2)', username, hash_code)
        info_logger.debug(f"@{username} was added to 'Twitter Users'")
    except Exception as e:
        db_logger.error(f"Error executing database query: {e}")


async def add_guild(guild, conn):

    try:
       await conn.execute('INSERT INTO guilds VALUES ($1)', guild.id)
       info_logger.debug(f"The guild '{guild.name}' was successfully added to the database.")
    except Exception as e:
        db_logger.info(f"Error executing database query: {e}")


async def add_channel(channel, conn):

    if not await guild_in_db(channel.guild.id, conn):
        await add_guild(channel.guild, conn)

    (webhook_id, webhook_token) = await create_webhook(channel)

    try:
        await conn.execute('INSERT INTO channels VALUES ($1, $2, $3, $4)', channel.id, webhook_id, webhook_token, channel.guild.id)
        info_logger.debug(f"Channel #{channel.name} from guild '{channel.guild.name}' was successfully added to the database.")
    except Exception as e:
        db_logger.error(f"Error executing database query: {e}")


async def add_sub(username, channel, conn):

    try:
        await conn.execute('INSERT INTO subs VALUES ($1, $2)', username, channel.id)
        info_logger.debug(f"#{channel.name} from guild '{channel.guild.name}' has now subbed to @{username}.")
    except Exception as e:
        db_logger.error(f"Error executing database query: {e}")


async def list_sub(channel, conn):

    user_list = await conn.fetch('SELECT "username" FROM subs where "channelId" = ($1)', channel.id)
    return user_list


async def remove_sub(username, channel, conn):
    
    try:
        if username != '<All>':
            await conn.execute('DELETE FROM subs WHERE "username" = ($1) AND "channelId" = ($2)', username, channel.id)
            info_logger.debug(f"#{channel.name} from guild '{channel.guild.name}' has now unsubbed to @{username}.")
        else:
            await conn.execute('DELETE FROM subs WHERE "channelId" = ($1)', channel.id)
            info_logger.debug(f"#{channel.name} from guild '{channel.guild.name}' has now unsubbed to all active subsciptions.")
    except Exception as e:
        db_logger.error(f"Error executing database query: {e}")
            


async def remove_guild(guild_id, conn):

    try:
        await conn.execute('DELETE FROM guilds WHERE  "guildId" = ($1)', guild_id)
        info_logger.debug(f"Guild with id '{guild_id}' was removed from the database due to having no active subscriptions")
    except Exception as e:
        db_logger.error(f"Error executing database query: {e}")       


async def remove_twitterUser(username, conn):

    try:
        await conn.execute('DELETE FROM twitterUsers WHERE  "username" = ($1)', username)
        info_logger.debug(f"Twitter user '@{username}' was removed from the database due to having no active subscriptions")
    except Exception as e:
        db_logger.error(f"Error executing database query: {e}")
        

##### Main bot functions #####

# Sanity Check

async def sanity_check(joinedGuilds):

    logger.info('Starting sanity check...')

    guilds = [joinedGuilds[i].id for i in range(len(joinedGuilds))]

    conn = await create_connection()

    guild_count = 0
    twitterUsers_count = 0

    active_guilds = await fetch_guild_lists(conn)

    if len(active_guilds) > 0:
        for guild_id in active_guilds:
            if guild_id[0] not in guilds:
                await remove_guild(guild_id[0], conn)
                guild_count += 1

    active_twitterUsers = await fetch_user_lists(conn)
    users = [user[0] for user in active_twitterUsers]
    subscribed_twitterUsers = await fetch_subscribed_users(conn)
    subbed_users = [user[0] for user in subscribed_twitterUsers]

    if len(subbed_users) > 0:
        for i in range(len(users)):
            if users[i] not in subbed_users:
                await remove_twitterUser(users[i], conn)
                twitterUsers_count += 1
        
    await close_connection(conn)
    logger.info(f"{guild_count} servers removed")
    logger.info(f"{twitterUsers_count} users removed")
    logger.info("Sanity check over")
    return


# Subscription functions

async def create_subscription(users, channel):

    msg = ''
    conn = await create_connection()

    for user in users.split():

        feed = feedparser.parse(f'https://nitter.woodland.cafe/{user}/with_replies/rss')
        if not feed.entries:
            msg += f"No twitter users found for ``@{user}``. Please check and try again\n"
            continue
        
        user = get_username(feed.feed.title)
        hash_code = create_hash(feed.entries[0])

        if not await sub_in_db(user, channel.id, conn):
            if not await username_in_db(user, conn):
                await add_user(user, hash_code, conn)
            if not await channel_in_db(channel.id, conn):
                await add_channel(channel, conn)
        else:
            msg += f"There is already an ongoing subscription for ``@{user}`` in <#{channel.id}>\n"
            continue

        await add_sub(user, channel, conn)
        msg += f"<#{channel.id}> is now subscribed to ``@{user}``.\n"

    await close_connection(conn)
    return msg


async def remove_subscription(username, channel):

    conn = await create_connection()

    if not await channel_in_sub(channel.id, conn):
        await close_connection(conn)
        return f"<#{channel.id}> has no active subscriptions."
    elif username == '<All>':
        await remove_sub(username, channel, conn)
        await close_connection(conn)
        return f"Successfully removed all active subscriptions in <#{channel.id}>"
    elif not await sub_in_db(username, channel.id, conn):
        await close_connection(conn)
        return f"``@{username}`` was not in the list of subscriptions for <#{channel.id}>"
    else:
        await remove_sub(username, channel, conn)
        await close_connection(conn)
        return f"Successfully unsubscribed to ``@{username}``"


async def list_subscriptions(channel):

    conn = await create_connection()

    if not await channel_in_sub(channel.id, conn):
        await close_connection(conn)
        return f"<#{channel.id}> has no active subscriptions."
    else:
        user_list = await list_sub(channel, conn)
        subs = ''
        count = len(user_list) + 1

        for i in range(count - 1):
            subs += f'{i+1}) ``@{user_list[i][0]}`` (https://twitter.com/{user_list[i][0]}/)\n'

        list_embed = discord.Embed(
                        title=f'**{count-1} Subscriptions**',
                        description=subs,
                        color=0x000000
                    )
        
        await close_connection(conn)
        return list_embed


# Update Function
    
async def get_updates():

    tweets = dict()
    subscription_webhooks = dict()

    logger.info("--- Retrieving new tweets ---")

    conn = await create_connection()

    user_hash_list = await fetch_user_hash_lists(conn)

    for (user, stored_hash) in user_hash_list:

        feed = feedparser.parse(f'https://nitter.woodland.cafe/{user}/with_replies/rss')
        if feed.entries:

            tweets[user] = list()

            name = feed.feed.title
            avatar_url = feed.feed.image['href']

            add = False
            no_of_tweets = len(feed.entries)
            while no_of_tweets > 0:
                if not add:
                    compare_hash = create_hash(feed.entries[no_of_tweets-1])
                    if compare_hash == stored_hash:
                        add = True
                else:
                    msg = generate_message(name, feed.entries[no_of_tweets-1])
                    tweets[user].append((msg, name, avatar_url))
                no_of_tweets -= 1
            if not add:                                                 # for sending just the latest tweet if no matching hash found
                msg = generate_message(name, feed.entries[0])
                tweets[user].append((msg, name, avatar_url))

            new_hash = create_hash(feed.entries[0])
            if stored_hash != new_hash:
                await update_hash(user, new_hash, conn)

        subscription_webhooks[user] = await fetch_subbed_webhook_details(conn, user)
    
    await close_connection(conn)

    logger.info("--- Finished retrieving new tweets ---")

    return (tweets, subscription_webhooks)


# Misc Functions

async def get_latest_tweet(username, channel):
    
    feed = feedparser.parse(f'https://nitter.woodland.cafe/{username}/with_replies/rss')

    if not feed.entries:
        return False
    
    name = feed.feed.title
    username = get_username(name)
    avatar_url = feed.feed.image['href']
    message = generate_message(name, feed.entries[0])
    channel_id = channel.id

    conn = await create_connection()

    try:
        check = await fetch_webhook_details(conn, channel_id)

        if not check:
            await add_channel(channel, conn)
            check = await fetch_webhook_details(conn, channel_id)
            (webhook_id, webhook_token) = check[0]
        else:
            (webhook_id, webhook_token) = check[0]
    
    except Exception as e:
        db_logger.error(f"Error executing database query: {e}")

    finally:
        await close_connection(conn)


    return (message, name, avatar_url, webhook_id, webhook_token)

