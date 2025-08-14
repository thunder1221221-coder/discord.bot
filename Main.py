from dotenv import load_dotenv
load_dotenv()

import discord
from discord.ext import commands, tasks
from discord import app_commands, Interaction, VoiceChannel, Member
from dotenv import load_dotenv
import os
import asyncio
import random
import json

load_dotenv()
TOKEN = os.getenv("TOKEN")
GUILD_ID = 1286717617821847624 # Your Discord Server ID

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True

bot = commands.Bot(command_prefix="/", intents=intents)
tree = bot.tree

queue = []
queued_users = set()
team_vcs = []
points = {}

# Load points if stored
if os.path.exists("points.json"):
    with open("points.json", "r") as f:
        points = json.load(f)


def save_points():
    with open("points.json", "w") as f:
        json.dump(points, f)


def get_team_size():
    size = len(queue)
    return size // 2 if size % 2 == 0 else (size - 1) // 2


@bot.event
async def on_ready():
    await tree.sync(guild=discord.Object(id=GUILD_ID))
    print(f"✅ Logged in as {bot.user}")
    print("✅ Synced slash commands.")


@tree.command(name="start", description="Start a match queue", guild=discord.Object(id=GUILD_ID))
async def start(interaction: Interaction):
    queue.clear()
    queued_users.clear()

    embed = discord.Embed(title="Match Queue", description="Click the button below to join the queue. Only users in a VC will be accepted.", color=discord.Color.blue())
    view = JoinQueueView(interaction)
    await interaction.response.send_message(embed=embed, view=view)


class JoinQueueView(discord.ui.View):
    def __init__(self, interaction: Interaction):
        super().__init__(timeout=None)
        self.interaction = interaction
        self.message = None

    @discord.ui.button(label="Join Queue", style=discord.ButtonStyle.green)
    async def join(self, interaction: Interaction, button: discord.ui.Button):
        user = interaction.user
        voice = user.voice

        if not voice or not voice.channel:
            await interaction.response.send_message("You must be in a VC to join the queue.", ephemeral=True)
            return

        if user.id in queued_users:
            await interaction.response.send_message("You already joined the queue!", ephemeral=True)
            return

        queue.append(user)
        queued_users.add(user.id)

        size = len(queue)
        team_size = get_team_size()
        total = team_size * 2

        content = f"**{size} out of {total} players have joined the queue.**"
        if self.message:
            await self.message.edit(content=content)
        else:
            self.message = await interaction.channel.send(content)

        await interaction.response.send_message("You joined the queue!", ephemeral=True)


@tree.command(name="start_random", description="Start match with random teams", guild=discord.Object(id=GUILD_ID))
async def start_random(interaction: Interaction):
    if len(queue) < 2:
        await interaction.response.send_message("Not enough players in the queue.", ephemeral=True)
        return

    random.shuffle(queue)
    team_size = get_team_size()
    team1 = queue[:team_size]
    team2 = queue[team_size:team_size*2]

    guild = interaction.guild
    team1_vc = await guild.create_voice_channel("Team 1")
    team2_vc = await guild.create_voice_channel("Team 2")
    team_vcs.extend([team1_vc, team2_vc])

    for member in team1:
        await member.move_to(team1_vc)
    for member in team2:
        await member.move_to(team2_vc)

    await interaction.response.send_message("Teams created and moved to temporary voice channels!", ephemeral=True)


@tree.command(name="win", description="Award points to the winning team", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(winners="Mention the winning team or users")
async def win(interaction: Interaction, winners: str):
    mentioned = interaction.user.mention in winners or any(user.mention in winners for user in queue)
    if not mentioned:
        await interaction.response.send_message("Mention the players or teams.", ephemeral=True)
        return

    win_ids = [user.id for user in queue if user.mention in winners]
    lose_ids = [user.id for user in queue if user.id not in win_ids]

    for uid in win_ids:
        points[str(uid)] = points.get(str(uid), 0) + 10

    for uid in lose_ids:
        points[str(uid)] = points.get(str(uid), 0) - 1

    save_points()

    # Move all players to general VC
    general = discord.utils.get(interaction.guild.voice_channels, name="General")
    if general:
        for member in queue:
            if member.voice:
                await member.move_to(general)

    # Delete temp VCs
    for vc in team_vcs:
        await vc.delete()
    team_vcs.clear()

    await interaction.response.send_message("Points updated and players moved to General. Temporary VCs deleted.", ephemeral=True)


@tree.command(name="leaderboard", description="Show the leaderboard", guild=discord.Object(id=GUILD_ID))
async def leaderboard(interaction: Interaction):
    if not points:
        await interaction.response.send_message("No points yet!", ephemeral=True)
        return

    sorted_points = sorted(points.items(), key=lambda x: x[1], reverse=True)
    description = "\n".join([f"{idx+1}. <@{uid}> - {score} points" for idx, (uid, score) in enumerate(sorted_points)])
    embed = discord.Embed(title="Leaderboard", description=description, color=discord.Color.gold())
    await interaction.response.send_message(embed=embed)

@tree.command(name="register", description="Register your team for the tournament", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(
    team_name="Team name",
    player1="Player 1",
    player2="Player 2",
    player3="Player 3",
    player4="Player 4",
    player5="Player 5",
    player6="Player 6"
)
async def register(
    interaction: discord.Interaction,
    team_name: str,
    player1: discord.Member = None,
    player2: discord.Member = None,
    player3: discord.Member = None,
    player4: discord.Member = None,
    player5: discord.Member = None,
    player6: discord.Member = None
):
    await interaction.response.defer(ephemeral=True)

    members = [interaction.user]
    for player in [player1, player2, player3, player4, player5, player6]:
        if player and player not in members:
            members.append(player)

    # Assign "Registered" role
    registered_role = discord.utils.get(interaction.guild.roles, name="Registered")
    if not registered_role:
        await interaction.followup.send("❌ 'Registered' role not found.", ephemeral=True)
        return

    for member in members:
        try:
            await member.add_roles(registered_role)
        except Exception as e:
            print(f"Error assigning role to {member.name}: {e}")

    # Send message in verification channel
        verified_channel = discord.utils.get(interaction.guild.text_channels, name="♧・｜╴legacy-clash-registered-teams")

        mentions = ", ".join(member.mention for member in members)
        await verified_channel.send(f"✅ **Team Registered:** `{team_name}`\n👥 Members: {mentions}")

    await interaction.followup.send(f"✅ Team `{team_name}` registered successfully!", ephemeral=True)



bot.run(TOKEN)
