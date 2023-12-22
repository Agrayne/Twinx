import discord
from discord import default_permissions
from discord.ext import tasks, commands
import aiohttp

import utils

##################################################################

bot = discord.Bot()


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
async def remove(ctx, username: discord.Option(str, default = None, description='Twitter handle'), all: discord.Option(bool, default = False, description='Remove all subscriptions')):


    await ctx.defer()
    if username == None and not all:
        await ctx.respond("Enter a username or set 'all' to True")
    if username != None and all:
        await ctx.respond("Leave username blank if you want to remove all subscriptions")
        return
    if username != None:
        msg = await utils.remove_subscription(username, ctx.channel, all=all)
    else:
        msg = await utils.remove_subscription(username, ctx.channel, all=all)
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
        
@tasks.loop(minutes=utils.UPDATE_INTERVAL)
async def check_updates():

    tweets, subscription_webhooks = await utils.get_updates()

    for user in tweets.keys():

        if not tweets[user]:
            continue

        for (msg, name, avatar_url) in tweets[user]:

            for (webhook_id, webhook_token, channel_id) in subscription_webhooks[user]:

                async with aiohttp.ClientSession() as session:
                    webhook = discord.Webhook.partial(webhook_id, webhook_token, session = session)
                    try:
                        await webhook.send(content = msg, username = name, avatar_url = avatar_url)
                    except discord.errors.NotFound as e:
                        (webhook_id, webhook_token) = await utils.update_webhook(bot.get_channel(channel_id))
                        webhook = discord.Webhook.partial(webhook_id, webhook_token, session = session)
                        await webhook.send(content = msg, username = name, avatar_url = avatar_url)
                    except Exception as e:
                        utils.logger.error(f"Error sending message through the webhook or creating a new one: {e}")

    print('Successfully Updated')

@check_updates.before_loop
async def before_check_updates():
    await bot.wait_until_ready()


# Bot initialization

bot.add_application_command(subscription)

bot.run(utils.BOT_TOKEN)

