"""flow5ctl のアーキテクチャ図を .drawio として書き出す。

    uv run python tools/gen_architecture.py
    /Applications/draw.io.app/Contents/MacOS/draw.io --export --format svg \
        --border 14 --embed-svg-fonts false --theme auto \
        --output docs/architecture.svg docs/architecture.drawio

依存の事実は AST で抽出した import グラフに基づく。矢印はそこに実在する辺だけを描く。
図を README や設計文書から起こしてはいけない — それは意図であって実装ではない。

ラベルは draw.io の HTML ラベル（html=1）を使う。html=0 だと改行が効かず幅で
折り返されるだけになる。ただし HTML ラベルにすると draw.io は SVG を
foreignObject で書き出すので、それを落とすビューアではラベルが消える。
そのため docs には PNG も併せて置いている。

ラベルは HTML マークアップを含むが、mxCell の value は XML の「属性」なので
生の < を置くと不正な XML になり、draw.io はそのセルを黙って捨てる（帯だけ
残って箱が全部消える）。必ず html.escape を通すこと。そのぶん &#160; のような
実体参照も二重エスケープされるので、字下げには実文字の nbsp (\u00a0) を使う。
"""
import html
import pathlib

BOX = ("rounded=1;arcSize=8;whiteSpace=wrap;html=1;fillColor=#ffffff;strokeColor=#d3d3cd;"
       "fontSize=13;fontColor=#1a1a19;verticalAlign=middle;align=center;")
ENTRY = BOX.replace("#ffffff", "#eaf2fc").replace("#d3d3cd", "#2a78d6")
ADAPT = BOX.replace("#ffffff", "#fdeee7").replace("#d3d3cd", "#eb6834")
BAND = ("rounded=1;arcSize=6;whiteSpace=wrap;html=1;fillColor=#f4f4f1;strokeColor=#e3e3de;"
        "verticalAlign=top;align=left;spacingLeft=14;spacingTop=8;fontSize=11;fontColor=#6b6b66;")
RULE = ("rounded=1;arcSize=6;whiteSpace=wrap;html=1;fillColor=#e8f7f1;strokeColor=#1baf7a;"
        "align=left;verticalAlign=top;spacingLeft=14;spacingTop=10;fontSize=11.5;fontColor=#1a1a19;")
NOTE = "text;html=1;align=left;verticalAlign=top;fontSize=11;fontColor=#6b6b66;"
EDGE = ("edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;strokeColor=#8a8a85;strokeWidth=1.4;"
        "endArrow=block;endFill=1;")
DASH = EDGE + "dashed=1;"

cells: list[str] = []


def cell(ident: str, value: str, style: str, x: int, y: int, w: int, h: int) -> None:
    cells.append(
        '        <mxCell id="%s" value="%s" style="%s" vertex="1" parent="1">\n'
        '          <mxGeometry x="%d" y="%d" width="%d" height="%d" as="geometry" />\n'
        '        </mxCell>' % (ident, html.escape(value), style, x, y, w, h))


def edge(ident: str, src: str, dst: str, style: str = EDGE,
         points: list[tuple[int, int]] | None = None) -> None:
    geo = '          <mxGeometry relative="1" as="geometry" />\n'
    if points:
        pts = "".join('              <mxPoint x="%d" y="%d" />\n' % (x, y) for x, y in points)
        geo = ('          <mxGeometry relative="1" as="geometry">\n'
               '            <Array as="points">\n' + pts +
               '            </Array>\n'
               '          </mxGeometry>\n')
    cells.append(
        '        <mxCell id="%s" style="%s" edge="1" parent="1" source="%s" target="%s">\n'
        % (ident, style, src, dst) + geo + '        </mxCell>')


def two_line(name: str, role: str) -> str:
    """モジュール名と、その下に一段小さく役割。"""
    return ('<b>%s</b><br><font style="font-size:10.5px" color="#6b6b66">%s</font>'
            % (name, role))


# ---- 層の帯 ----
cell("b1", "入口 — 人と AI が触る面", BAND, 40, 40, 1040, 116)
cell("b2", "ユースケース — 手順を決める", BAND, 40, 196, 1040, 112)
cell("b3", "ドメイン — flow5 を知らない", BAND, 40, 348, 610, 222)
cell("b4", "アダプタ — flow5 の癖をここに閉じ込める", BAND, 680, 348, 400, 222)

# ---- 入口 ----
cell("cli", two_line("cli", "13 の verb。人が打つ"), ENTRY, 72, 76, 220, 62)
cell("mcp", two_line("mcp_server", "13 tool / 6 resource。AI が呼ぶ"), ENTRY, 322, 76, 250, 62)
cell("n1", "どちらも同じ usecases を呼ぶ。<br>CLI にできて MCP にできないことは無い。",
     NOTE, 606, 70, 330, 44)

# ---- ユースケース ----
cell("uc",
     "<b>define · edit · expand · analyze · trim · sweep · plot · gui</b><br>"
     '<font style="font-size:10.5px" color="#6b6b66">'
     "ガードレールを掛け、flow5 を2パスで走らせ、結果を results/ に残す</font>",
     BOX, 72, 222, 976, 62)

# ---- ドメイン ----
cell("model", two_line("model", "設計スキーマ Pydantic"), BOX, 66, 384, 172, 58)
cell("geom", two_line("geometry", "面積・MAC・重心"), BOX, 256, 384, 172, 58)
cell("advisor", two_line("advisor", "妥当性の帯・警告"), BOX, 446, 384, 180, 58)
cell("project", two_line("project", "design.yaml の入出力"), BOX, 66, 470, 172, 58)
cell("viz", two_line("viz", "図の描画"), BOX, 256, 470, 172, 58)
cell("n2", "この5つが flow5 を<br>import することは無い", NOTE, 452, 480, 170, 44)

# ---- アダプタ ----
cell("xmlgen", two_line("xmlgen", "flow5 方言だけを書く"), ADAPT, 700, 384, 176, 58)
cell("results", two_line("results", "壊れた CSV を読む"), ADAPT, 890, 384, 176, 58)
cell("markers", two_line("markers · summary", "成否判定・要約"), ADAPT, 700, 470, 176, 58)
cell("runner", two_line("runner · probe", "起動・版数検出"), ADAPT, 890, 470, 176, 58)

# ---- 外部プロセス ----
cell("flow5",
     "<b>flow5 7.57（外部プロセス）</b><br>"
     '<font style="font-size:10.5px" color="#6b6b66">'
     "XML を食わせて CSV を吐かせる。2パス必須</font>",
     BOX, 700, 620, 366, 60)

# ---- 不変条件 ----
cell("rules",
     "<b>コードで検証した不変条件</b><br><br>"
     "・ドメイン（model / geometry / advisor / project / viz）から<br>"
     "\u00a0\u00a0flow5 への import は <b>0 本</b>。だから flow5 が無い CI でも<br>"
     "\u00a0\u00a0テストが全部通る。<br><br>"
     "・入口から flow5 に届くのは probe（版数検出）だけ。破線がそれ。<br>"
     "\u00a0\u00a0解析本体は必ず usecases を経由する。<br><br>"
     "・errors は全モジュールが import するので図には描いていない。",
     RULE, 40, 620, 610, 166)

# ---- 依存の矢印（import する側 → される側）----
edge("e1", "cli", "uc")
edge("e2", "mcp", "uc")
edge("e3", "uc", "geom")
edge("e4", "uc", "xmlgen")
edge("e5", "advisor", "geom")
edge("e6", "runner", "flow5")
edge("e7", "mcp", "runner", DASH, points=[(1110, 132), (1110, 499)])

HEAD = ('<mxfile host="flow5ctl" type="device">\n'
        '  <diagram name="flow5ctl architecture" id="arch">\n'
        '    <mxGraphModel dx="1400" dy="900" grid="1" gridSize="10" guides="1" '
        'tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" '
        'pageWidth="1169" pageHeight="826" math="0" shadow="0">\n'
        '      <root>\n'
        '        <mxCell id="0" />\n'
        '        <mxCell id="1" parent="0" />\n')
TAIL = ('\n      </root>\n'
        '    </mxGraphModel>\n'
        '  </diagram>\n'
        '</mxfile>\n')

if __name__ == "__main__":
    out = pathlib.Path("docs/architecture.drawio")
    out.write_text(HEAD + "\n".join(cells) + TAIL, encoding="utf-8")
    print("書き出し", out.stat().st_size, "bytes ->", out)
