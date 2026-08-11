import io
import os
from PIL import Image, ImageDraw, ImageFont

CANVAS_W = 1000
CANVAS_H = 1500
PITCH_MARGIN = 50
HEADER_H = 90
PITCH_TOP = HEADER_H
PITCH_BOTTOM = CANVAS_H - HEADER_H
PITCH_LEFT = PITCH_MARGIN
PITCH_RIGHT = CANVAS_W - PITCH_MARGIN
PITCH_HALF_H = (PITCH_BOTTOM - PITCH_TOP) / 2
PITCH_W = PITCH_RIGHT - PITCH_LEFT

GRASS_LIGHT = (68, 154, 92)
GRASS_DARK = (61, 143, 84)
LINE_COLOR = (255, 255, 255, 180)
PLAYER_RADIUS = 32

_FONTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "assets", "fonts")


def _load_font(bold: bool, size: int) -> ImageFont.FreeTypeFont:
    filename = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    return ImageFont.truetype(os.path.join(_FONTS_DIR, filename), size)


FONT_TITLE = _load_font(bold=True, size=32)
FONT_FORMATION = _load_font(bold=False, size=22)
FONT_SUBTITLE = _load_font(bold=True, size=18)
FONT_NUMBER = _load_font(bold=True, size=26)
FONT_NAME = _load_font(bold=True, size=20)

UNCONFIRMED_COLOR = (255, 165, 0)


def lineup_confirmed(lineup: dict) -> bool:
    return (lineup.get("status") or "").strip().lower() == "confirmado"


def _text_color(hex_color: str) -> tuple[int, int, int]:
    hex_color = (hex_color or "#FFFFFF").lstrip("#")
    if len(hex_color) != 6:
        return (255, 255, 255)
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
    luminance = 0.299 * r + 0.587 * g + 0.114 * b
    return (0, 0, 0) if luminance > 140 else (255, 255, 255)


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    hex_color = (hex_color or "#CCCCCC").lstrip("#")
    if len(hex_color) != 6:
        return (204, 204, 204)
    return tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))


def _draw_pitch(draw: ImageDraw.ImageDraw):
    for i in range(10):
        stripe_top = PITCH_TOP + i * (PITCH_BOTTOM - PITCH_TOP) / 10
        stripe_bottom = PITCH_TOP + (i + 1) * (PITCH_BOTTOM - PITCH_TOP) / 10
        color = GRASS_LIGHT if i % 2 == 0 else GRASS_DARK
        draw.rectangle([PITCH_LEFT, stripe_top, PITCH_RIGHT, stripe_bottom], fill=color)

    box = [PITCH_LEFT, PITCH_TOP, PITCH_RIGHT, PITCH_BOTTOM]
    draw.rectangle(box, outline=LINE_COLOR, width=4)
    draw.line([PITCH_LEFT, PITCH_TOP + PITCH_HALF_H, PITCH_RIGHT, PITCH_TOP + PITCH_HALF_H], fill=LINE_COLOR, width=4)

    center_y = PITCH_TOP + PITCH_HALF_H
    center_x = PITCH_LEFT + PITCH_W / 2
    circle_r = PITCH_W * 0.14
    draw.ellipse([center_x - circle_r, center_y - circle_r, center_x + circle_r, center_y + circle_r], outline=LINE_COLOR, width=4)
    draw.ellipse([center_x - 6, center_y - 6, center_x + 6, center_y + 6], fill=LINE_COLOR)

    box_w = PITCH_W * 0.62
    box_h = PITCH_HALF_H * 0.28
    goal_w = PITCH_W * 0.32
    goal_h = PITCH_HALF_H * 0.11
    arc_r = PITCH_W * 0.13

    for edge_y, direction in ((PITCH_TOP, 1), (PITCH_BOTTOM, -1)):
        draw.rectangle([
            center_x - box_w / 2, min(edge_y, edge_y + direction * box_h),
            center_x + box_w / 2, max(edge_y, edge_y + direction * box_h),
        ], outline=LINE_COLOR, width=4)
        draw.rectangle([
            center_x - goal_w / 2, min(edge_y, edge_y + direction * goal_h),
            center_x + goal_w / 2, max(edge_y, edge_y + direction * goal_h),
        ], outline=LINE_COLOR, width=4)
        arc_center_y = edge_y + direction * box_h
        bbox = [center_x - arc_r, arc_center_y - arc_r, center_x + arc_r, arc_center_y + arc_r]
        if direction == 1:
            draw.arc(bbox, start=25, end=155, fill=LINE_COLOR, width=4)
        else:
            draw.arc(bbox, start=205, end=335, fill=LINE_COLOR, width=4)

    corner_r = 18
    for cx, cy, start in (
        (PITCH_LEFT, PITCH_TOP, 0), (PITCH_RIGHT, PITCH_TOP, 90),
        (PITCH_LEFT, PITCH_BOTTOM, 270), (PITCH_RIGHT, PITCH_BOTTOM, 180),
    ):
        draw.arc([cx - corner_r, cy - corner_r, cx + corner_r, cy + corner_r], start=start, end=start + 90, fill=LINE_COLOR, width=3)


HALFWAY_GAP = 0.15  # deja un colchón cerca de la línea de mitad de cancha para que las dos líneas de ataque no se pisen


def _player_pixel_pos(pitch_location: dict, attacks_downward: bool) -> tuple[float, float]:
    x = max(0, min(100, pitch_location.get("x", 50))) / 100 * (1 - HALFWAY_GAP)
    y = max(0, min(100, pitch_location.get("y", 50))) / 100
    px = PITCH_LEFT + y * PITCH_W
    if attacks_downward:
        py = PITCH_TOP + x * PITCH_HALF_H
    else:
        py = PITCH_BOTTOM - x * PITCH_HALF_H
    return px, py


def _draw_player(draw: ImageDraw.ImageDraw, player: dict, pos: tuple[float, float], fill_color: tuple, number_color: tuple):
    px, py = pos
    r = PLAYER_RADIUS
    draw.ellipse([px - r, py - r, px + r, py + r], fill=fill_color, outline=(255, 255, 255), width=3)

    number = str(player.get("jersey_num", "?"))
    bbox = draw.textbbox((0, 0), number, font=FONT_NUMBER)
    draw.text((px - (bbox[2] - bbox[0]) / 2, py - (bbox[3] - bbox[1]) / 2 - bbox[1]), number, font=FONT_NUMBER, fill=number_color)

    if player.get("is_captain"):
        badge_x, badge_y = px + r - 8, py - r + 8
        draw.ellipse([badge_x - 12, badge_y - 12, badge_x + 12, badge_y + 12], fill=(255, 205, 0), outline=(0, 0, 0), width=1)
        cbbox = draw.textbbox((0, 0), "C", font=FONT_FORMATION)
        draw.text((badge_x - (cbbox[2] - cbbox[0]) / 2, badge_y - (cbbox[3] - cbbox[1]) / 2 - cbbox[1] - 2), "C", font=FONT_FORMATION, fill=(0, 0, 0))

    name = player.get("player_short_name") or player.get("name") or "?"
    nbbox = draw.textbbox((0, 0), name, font=FONT_NAME)
    name_w = nbbox[2] - nbbox[0]
    label_y = py + r + 6
    draw.rectangle([px - name_w / 2 - 8, label_y, px + name_w / 2 + 8, label_y + 26], fill=(0, 0, 0, 160))
    draw.text((px - name_w / 2, label_y + 2), name, font=FONT_NAME, fill=(255, 255, 255))


def render_lineups(game: dict) -> io.BytesIO | None:
    """Genera un maquetado visual de la cancha con las formaciones titulares,
    estilo Promiedos: el equipo local abajo atacando hacia arriba, el visitante
    arriba atacando hacia abajo, encontrándose en la línea de mitad de cancha."""
    lineups = game.get("players", {}).get("lineups", {}).get("teams", [])
    if len(lineups) < 2:
        return None

    teams = game.get("teams", [{}, {}])
    image = Image.new("RGB", (CANVAS_W, CANVAS_H), (30, 30, 30))
    draw = ImageDraw.Draw(image, "RGBA")
    _draw_pitch(draw)

    for lineup in lineups:
        team_idx = lineup.get("team_num", 1) - 1
        if not (0 <= team_idx < len(teams)):
            continue
        team_data = teams[team_idx]
        colors = team_data.get("colors", {})
        fill_color = _hex_to_rgb(colors.get("color"))
        number_color = _text_color(colors.get("color"))
        attacks_downward = team_idx == 1

        for player in lineup.get("starting", []):
            pitch_location = player.get("pitch_location")
            if not pitch_location:
                continue
            pos = _player_pixel_pos(pitch_location, attacks_downward)
            _draw_player(draw, player, pos, fill_color, number_color)

        header = f"{team_data.get('short_name', 'Equipo')} ({lineup.get('formation', '?')})"
        hbbox = draw.textbbox((0, 0), header, font=FONT_TITLE)
        header_w = hbbox[2] - hbbox[0]
        header_x = (CANVAS_W - header_w) / 2
        header_y = 10 if team_idx == 1 else CANVAS_H - HEADER_H + 10
        draw.text((header_x, header_y), header, font=FONT_TITLE, fill=(255, 255, 255))

        if not lineup_confirmed(lineup):
            subtitle = "[Formación sin confirmar]"
            sbbox = draw.textbbox((0, 0), subtitle, font=FONT_SUBTITLE)
            subtitle_w = sbbox[2] - sbbox[0]
            subtitle_x = (CANVAS_W - subtitle_w) / 2
            subtitle_y = header_y + 42
            draw.text((subtitle_x, subtitle_y), subtitle, font=FONT_SUBTITLE, fill=UNCONFIRMED_COLOR)

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer
