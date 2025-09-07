from dataclasses import dataclass
from datetime import datetime

import pytz

from config.settings import settings

NONE_MESSAGE = "No anunciado"

@dataclass
class Fixture:
    local_team: str | None = None
    visiting_team: str | None = None
    competition: str | None = None
    date_time: datetime | None = None
    stadium: str | None = None
    referee: str | None = None
    tv_channels: str | None = None
    
    def to_description(self) -> str:
        """Build description string from fixture data"""
        description  = f"\t  ⚽\t{self.local_team} vs {self.visiting_team}\n"
        description += f"\t  🏆\t{self.competition}\n"
        description += f"\t  🏟️\t{self.stadium or NONE_MESSAGE}\n"
        description += f"\t  📅\t{self.date_time.strftime('%d/%m/%Y %H:%M')}\n"
        description += f"\t  ⚖️\t{self.referee or NONE_MESSAGE}\n"
        description += f"\t  📺\t{self.tv_channels or NONE_MESSAGE}\n"
        return description
    
    @classmethod
    def from_description(cls, description: str) -> 'Fixture':
        """Parse description string and return Fixture object"""
        lines = description.strip().split('\n')
        
        teams_line = None
        for line in lines:
            if line.startswith("⚽"):
                teams_line = line.replace("⚽", "").strip()
                break
        
        if not teams_line or " vs " not in teams_line:
            raise ValueError("Could not parse team information from description")
        
        local_team, visiting_team = teams_line.split(" vs ", 1)
        
        competition = None
        stadium = None
        referee = None
        tv_channels = None
        date_time = None
        
        for line in lines:
            line = line.strip()
            if line.startswith("🏆"):
                competition = line.replace("🏆", "").strip()
            elif line.startswith("🏟️"):
                stadium_value = line.replace("🏟️", "").strip()
                if stadium_value != NONE_MESSAGE:
                    stadium = stadium_value
            elif line.startswith("📅"):
                date_str = line.replace("📅", "").strip()
                try:
                    date_time = datetime.strptime(date_str, '%d/%m/%Y %H:%M')
                    tz = settings.TIMEZONE
                    date_time = tz.localize(date_time)
                except ValueError:
                    raise
            elif line.startswith("⚖️"):
                referee_value = line.replace("⚖️", "").strip()
                if referee_value != NONE_MESSAGE:
                    referee = referee_value
            elif line.startswith("📺"):
                tv_value = line.replace("📺", "").strip()
                if tv_value != NONE_MESSAGE:
                    tv_channels = tv_value
        
        return cls(
            local_team=local_team.strip(),
            visiting_team=visiting_team.strip(),
            competition=competition,
            date_time=date_time,
            stadium=stadium,
            referee=referee,
            tv_channels=tv_channels
        )
    
    def get_changes(self, other: 'Fixture') -> str | None:
        """Compare this fixture with another and return a description of changes"""
        changes = []

        if self.local_team != other.local_team:
            changes.append(self.format_change("🏠", self.local_team, other.local_team))
            
        if self.visiting_team != other.visiting_team:
            changes.append(self.format_change("🧳", self.visiting_team, other.visiting_team))
            
        if self.competition != other.competition:
            changes.append(self.format_change("🏆", self.competition, other.competition))
            
        if self.date_time != other.date_time:
            changes.append(
                self.format_change("📅",
                    self.date_time.strftime('%d/%m/%Y %H:%M'),
                    other.date_time.strftime('%d/%m/%Y %H:%M')))
            
        if self.stadium != other.stadium:
            changes.append(self.format_change("🏟️", self.stadium, other.stadium))
            
        if self.referee != other.referee:
            changes.append(self.format_change("⚖️", self.referee, self.referee))
            
        if self.tv_channels != other.tv_channels:
            changes.append(self.format_change("📺", self.tv_channels, other.tv_channels))
        
        if changes:
            return "\n".join(f"{change}" for change in changes)
        else:
            return None
    
    def __eq__(self, other):
        """Compare two fixtures for equality"""
        if not isinstance(other, Fixture):
            return False
        return (
            self.local_team == other.local_team and
            self.visiting_team == other.visiting_team and
            self.competition == other.competition and
            self.date_time == other.date_time and
            self.stadium == other.stadium and
            self.referee == other.referee and
            self.tv_channels == other.tv_channels
        )
    
    @staticmethod
    def format_change(id: str, old: str | None, new: str | None) -> str:
        return f"{id}:\t{old or NONE_MESSAGE} **->** {new or NONE_MESSAGE}"