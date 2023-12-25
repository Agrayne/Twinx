import discord
from discord import default_permissions
from discord.ext import tasks, commands
import aiohttp

import utils


bot = discord.Bot()


# Secondary Functions

async def get_subbed_users(ctx: discord.AutocompleteContext):
    '''This function will be used to get subbed user list when using the remove command'''
    users = await utils.fetch_subbed_users_by_channel(ctx.interaction.channel.id)
    if not users:
        users.append('---No subscriptions---')
        return users
    users.insert(0, '<All>')
    return users


# Bot Events

@bot.event
async def on_ready():
    await utils.sanity_check(bot.guilds)
    utils.logger.info(f"{bot.user} is ready and online!")
    check_updates.start()


@bot.event
async def on_application_command_error(ctx, error):
    
    if isinstance(error, commands.errors.MissingPermissions):
        await ctx.respond("You do not have the permissions to use this command.")


# Misc Commands

@bot.command(description="Sends the bot's latency.") # this decorator makes a slash command
async def ping(ctx): # a slash command will be created with the name "ping"
    await ctx.respond(f"Pong! Latency is {bot.latency}")


@bot.command(description="Sends the latest tweet of the user.")
async def tweet(ctx, username: discord.Option(str, required = True), description= 'Twitter handle'):
    await ctx.defer()

    result = await utils.get_latest_tweet(username, channel=ctx.channel)

    if not result:
        await ctx.respond('No tweets found.\nSite error or Invalid Username')
    else:
        (message, name, avatar_url, webhook_id, webhook_token) = result
        await ctx.respond(f"Fetching latest tweet from {name}...", delete_after=5)

        async with aiohttp.ClientSession() as session:
            webhook = discord.Webhook.partial(webhook_id, webhook_token, session = session)

            try:
                await webhook.send(content = message, username = name, avatar_url = avatar_url)
            except discord.errors.NotFound as e:
                (webhook_id, webhook_token) = await utils.update_webhook(ctx.channel)
                webhook = discord.Webhook.partial(webhook_id, webhook_token, session = session)
                await webhook.send(content = message, username = name, avatar_url = avatar_url)
            except Exception as e:
                utils.logger.error(f"Error sending message through the webhook or creating a new one: {e}")


# Subscription Commands

subscription = discord.SlashCommandGroup('subscription', 'Commands related to twitter user subscription')

@subscription.command(description='Subscribe to a twitter user')
@commands.has_permissions(manage_channels=True)
async def add(ctx, username: discord.Option(str, required = True, description= 'Twitter handle')):
    
    await ctx.defer()
    msg =  await utils.create_subscription(username, ctx.channel)
    await ctx.respond(msg)


@subscription.command(description='Unsubscribe to a twitter user')
@commands.has_permissions(manage_channels=True)
async def remove(ctx, username: discord.Option(str, autocomplete=discord.utils.basic_autocomplete(get_subbed_users), required=True)):

    if username == '---No subscriptions---':
        await ctx.respond(f'<#{ctx.channel.id}> has no active subscriptions.')

    await ctx.defer()
    msg = await utils.remove_subscription(username, ctx.channel)
    await ctx.respond(msg)


@subscription.command(description='Lists all active subscriptions from the current channel')
async def list(ctx):

    await ctx.defer()
    msg = await utils.list_subscriptions(ctx.channel)
    if isinstance(msg, str):
        await ctx.respond(msg)
    else:
        await ctx.respond(embed=msg)


# Update events
UPDATE_INTERVAL = int(utils.UPDATE_INTERVAL)
@tasks.loop(minutes=UPDATE_INTERVAL)
async def check_updates():

    tweets, subscription_webhooks = await utils.get_updates()
    webhook_updates = []

    for user in tweets.keys():
        if not tweets[user]:
            continue

        for (msg, name, avatar_url) in tweets[user]:
            for (webhook_id, webhook_token, channel_id) in subscription_webhooks[user]:
                webhook_updates.append((webhook_id, webhook_token, msg, name, avatar_url, channel_id))

    async with aiohttp.ClientSession() as session:
        new_tweets = len(webhook_updates)
        for (webhook_id, webhook_token, msg, name, avatar_url, channel_id) in webhook_updates:
                webhook = discord.Webhook.partial(webhook_id, webhook_token, session=session)
                try:
                    await webhook.send(content=msg, username=name, avatar_url=avatar_url)
                except discord.errors.NotFound:
                    (webhook_id, webhook_token) = await utils.update_webhook(bot.get_channel(channel_id))
                    webhook = discord.Webhook.partial(webhook_id, webhook_token, session=session)
                    await webhook.send(content=msg, username=name, avatar_url=avatar_url)
                except Exception as e:
                    utils.logger.error(f"Error sending message through the webhook or creating a new one: {e}")

    utils.logger.info(f'Successfully Updated: Sent {new_tweets} new tweets')

@check_updates.before_loop
async def before_check_updates():
    await bot.wait_until_ready()


# Bot initialization

bot.add_application_command(subscription)

bot.run(utils.BOT_TOKEN)

