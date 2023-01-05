import discord
from discord.ext import commands
import asyncio
import openpotd


class MenuManager(commands.Cog):
    def __init__(self, bot: openpotd.OpenPOTD):
        self.bot = bot
        self.active_menus = {}

    # Deletes menus after a certain time.
    async def delete_after(self, timeout: int, menu_id):
        await asyncio.sleep(timeout)
        if menu_id in self.active_menus:
            await self.active_menus[menu_id].remove()
            del self.active_menus[menu_id]

    async def new_menu(self, ctx: commands.Context, pages: list, cur_page: int = 0, timeout: int = 60):
        menu = Menu(ctx, pages, cur_page, timeout)
        await menu.open()
        self.active_menus[menu.message.id] = menu
        await self.delete_after(timeout, menu.message.id)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.user_id == self.bot.user.id:
            return
        if payload.message_id in self.active_menus:
            if payload.emoji.name == '◀':
                await self.active_menus[payload.message_id].previous_page(payload.user_id)
            elif payload.emoji.name == '⏹':
                if payload.message_id in self.active_menus \
                        and self.active_menus[payload.message_id].owner == payload.user_id:
                    await self.delete_after(0, payload.message_id)
            elif payload.emoji.name == '▶':
                await self.active_menus[payload.message_id].next_page(payload.user_id)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        if payload.user_id == self.bot.user.id:
            return
        if payload.message_id in self.active_menus:
            if payload.emoji.name == '◀':
                await self.active_menus[payload.message_id].previous_page(payload.user_id)
            elif payload.emoji.name == '⏹':
                if payload.message_id in self.active_menus \
                        and self.active_menus[payload.message_id].owner == payload.user_id:
                    await self.delete_after(0, payload.message_id)
            elif payload.emoji.name == '▶':
                await self.active_menus[payload.message_id].next_page(payload.user_id)


class Menu:

    def __init__(self, ctx: commands.Context, pages: list, cur_page: int = 0, timeout: int = 60):
        assert not len(pages) == 0
        self.ctx = ctx
        self.pages = pages
        self.message = None
        self.id = ctx.message.id
        self.cur_page = cur_page
        self.owner = ctx.author.id

    async def open(self):
        self.message = await self.ctx.send(embed=self.pages[self.cur_page])
        await self.message.add_reaction('◀')
        await self.message.add_reaction('⏹')
        await self.message.add_reaction('▶')

    async def next_page(self, user_id):
        if self.cur_page < len(self.pages) - 1 and user_id == self.owner:
            self.cur_page += 1
            await self.message.edit(embed=self.pages[self.cur_page])

    async def previous_page(self, user_id):
        if self.cur_page > 0 and user_id == self.owner:
            self.cur_page -= 1
            await self.message.edit(embed=self.pages[self.cur_page])

    async def remove(self):
        try:
            await self.message.clear_reactions()
        except discord.Forbidden as e:
            await self.message.remove_reaction('◀', self.ctx.me)
            await self.message.remove_reaction('⏹', self.ctx.me)
            await self.message.remove_reaction('▶', self.ctx.me)


async def setup(bot: openpotd.OpenPOTD):
    await bot.add_cog(MenuManager(bot))
