import logging
import discord
from discord.ext import commands
import asyncio
import openpotd

active_menus = {}


# Deletes menus after a certain time.
async def delete_after(timeout: int, id):
    await asyncio.sleep(timeout)
    await active_menus[id].remove()


class MenuManager(commands.Cog):
    def __init__(self, bot: openpotd.OpenPOTD):
        self.bot = bot

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        logging.info('added reaction' + payload.emoji.name)
        if payload.user_id == self.bot.user.id:
            return
        logging.info(str(active_menus))
        if payload.message_id in active_menus:
            if payload.emoji.name == '◀':
                await active_menus[payload.message_id].previous_page()
            elif payload.emoji.name == '⏹':
                await active_menus[payload.message_id].remove()
            elif payload.emoji.name == '▶':
                await active_menus[payload.message_id].next_page()

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        logging.info('removed reaction' + payload.emoji.name)
        if payload.user_id == self.bot.user.id:
            return
        if payload.message_id in active_menus:
            if payload.emoji.name == '◀':
                await active_menus[payload.message_id].previous_page()
            elif payload.emoji.name == '⏹':
                await active_menus[payload.message_id].remove()
            elif payload.emoji.name == '▶':
                await active_menus[payload.message_id].next_page()


class Menu:

    def __init__(self, ctx: commands.Context, pages: list, cur_page: int = 0, timeout: int = 60):
        assert not len(pages) == 0
        self.ctx = ctx
        self.pages = pages
        self.message = None

        logging.info('Created menu. ')
        self.id = ctx.message.id
        self.cur_page = cur_page
        active_menus[self.id] = self
        ctx.bot.loop.create_task(delete_after(timeout, self.id))

    async def open(self):
        logging.info(f'Opening menu {self.id}')
        self.message = await self.ctx.send(embed=self.pages[self.cur_page])
        await self.message.add_reaction('◀')
        await self.message.add_reaction('⏹')
        await self.message.add_reaction('▶')

    async def next_page(self):
        logging.info('Next page')
        if self.cur_page < len(self.pages) - 1:
            self.cur_page += 1
            await self.ctx.message.edit(embed=self.pages[self.cur_page])

    async def previous_page(self):
        logging.info('Previous page')
        if self.cur_page > 0:
            self.cur_page -= 1
            await self.message.edit(embed=self.pages[self.cur_page])

    async def remove(self):
        logging.info('Removing')
        await self.message.remove_reaction('◀', self.ctx.me)
        await self.message.remove_reaction('⏹', self.ctx.me)
        await self.message.remove_reaction('▶', self.ctx.me)
        del active_menus[self.id]


def setup(bot: openpotd.OpenPOTD):
    bot.add_cog(MenuManager(bot))
