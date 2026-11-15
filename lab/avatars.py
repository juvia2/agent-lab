"""에이전트 프로필 그림(도형 생물). 관제 화면과 디스코드 봇 프로필이 같은 그림을 쓴다.

svg(role)          → 색을 CSS 클래스(.d 원판 · .b 몸 · .bs 몸 선 · .f 접힌 면)로 남긴 SVG. 관제 화면이 --h 로 칠한다.
svg(role, "dark")  → 색을 직접 박은 단독 SVG(PNG 변환·디스코드용).
"""
from __future__ import annotations

HUE = {"director": 40, "linguist": 345, "cogsci": 295, "lm": 260, "statistician": 220, "corpus": 190,
       "practitioner": 160, "developer": 85, "documenter": 15, "tester": 125}

COLORS = {  # 원판, 몸, 접힌 면
    "dark": ("hsl({h} 28% 21%)", "hsl({h} 52% 60%)", "hsl({h} 50% 80%)"),
    "light": ("hsl({h} 50% 93%)", "hsl({h} 50% 52%)", "hsl({h} 55% 78%)"),
}


def _eyes(y: float = 33, dx: float = 7) -> str:
    return "".join(f'<circle cx="{32 + s * dx}" cy="{y}" r="3.6" fill="#fff"/>'
                   f'<circle cx="{32 + s * dx + .8}" cy="{y + .6}" r="1.8" fill="#1b1b19"/>' for s in (-1, 1))


# 64x64 좌표. fill="B" 몸, stroke="B" 몸 색 선, fill="F" 접힌 면 — 한 요소에 둘을 같이 쓰지 않는다.
SHAPES = {
    "director": '<path d="M32 18V11" stroke="B" stroke-width="3" stroke-linecap="round"/><circle cx="32" cy="10" r="3.5" fill="B"/>'
                '<rect x="16" y="18" width="32" height="30" rx="11" fill="B"/>' + _eyes(32),
    "linguist": '<path d="M14 22a8 8 0 0 1 8-8h20a8 8 0 0 1 8 8v14a8 8 0 0 1-8 8H30l-9 7 1-7a8 8 0 0 1-8-8z" fill="B"/>' + _eyes(29),
    "cogsci": '<path d="M20 47c-6 0-9-5-7-10-4-3-3-10 2-12 0-6 6-9 11-7 3-4 10-4 13 0 5-2 11 1 11 7 5 2 6 9 2 12 2 5-1 10-7 10z" fill="B"/>'
              + _eyes(33),
    "lm": '<path d="M29 11.7a6 6 0 0 1 6 0l13.3 7.7a6 6 0 0 1 3 5.2v14.8a6 6 0 0 1-3 5.2L35 52.3a6 6 0 0 1-6 0L15.7 44.6a6 6 0 0 1-3-5.2V24.6'
          'a6 6 0 0 1 3-5.2z" fill="B"/>' + _eyes(31),
    "statistician": '<path d="M12 49C16 49 18 15 32 15S48 49 52 49Z" fill="B"/>' + _eyes(34, 6),
    "corpus": '<rect x="16" y="40" width="32" height="9" rx="3" fill="B" opacity=".55"/>'
              '<rect x="16" y="34" width="32" height="9" rx="3" fill="B" opacity=".78"/>'
              '<rect x="16" y="14" width="32" height="23" rx="8" fill="B"/>' + _eyes(25),
    "practitioner": '<rect x="28" y="9" width="8" height="5" rx="1.5" fill="B"/>'
                    '<path d="M45 18l3-3" stroke="B" stroke-width="3" stroke-linecap="round"/>'
                    '<circle cx="32" cy="34" r="18" fill="B"/>' + _eyes(34),
    "developer": '<path d="M12 26l-5 6 5 6M52 26l5 6-5 6" stroke="B" stroke-width="3.2" fill="none" stroke-linecap="round" '
                 'stroke-linejoin="round"/><rect x="16" y="17" width="32" height="30" rx="6" fill="B"/>' + _eyes(32),
    "documenter": '<path d="M18 12h20l10 10v28a2 2 0 0 1-2 2H18a2 2 0 0 1-2-2V14a2 2 0 0 1 2-2z" fill="B"/>'
                  '<path d="M38 12v8a2 2 0 0 0 2 2h8" fill="F"/>' + _eyes(32),
    "tester": '<path d="M32 11l17 6v13c0 11-7 18-17 22-10-4-17-11-17-22V17z" fill="B"/>' + _eyes(29),
}


def svg(role: str, theme: str | None = None) -> str:
    if role not in SHAPES:
        return ""
    body = SHAPES[role]
    if theme is None:
        disc = 'class="d"'
        body = body.replace('fill="B"', 'class="b"').replace('stroke="B"', 'class="bs"').replace('fill="F"', 'class="f"')
    else:
        d, b, f = (c.format(h=HUE[role]) for c in COLORS[theme])
        disc = f'fill="{d}"'
        body = body.replace('"B"', f'"{b}"').replace('"F"', f'"{f}"')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><circle cx="32" cy="32" r="31" {disc}/>'
            f'<g transform="translate(32 33) scale(.86) translate(-32 -32)">{body}</g></svg>')
