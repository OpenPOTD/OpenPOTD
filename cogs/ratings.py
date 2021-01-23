import discord
from discord.ext import commands

import openpotd


class Ratings(commands.Cog):
    def __init__(self, bot: openpotd.OpenPOTD):
        self.bot = bot


def setup(bot: openpotd.OpenPOTD):
    bot.add_cog(Ratings(bot))
