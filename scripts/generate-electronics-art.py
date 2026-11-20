"""Generate original, self-contained electronics artwork. No downloaded product images."""
from pathlib import Path

DEST = Path(__file__).resolve().parents[1] / "frontend/public/products/electronics"
PALETTES = {
    "black": ("#252b32", "#535e69", "#10161d", "#939ea9"),
    "silver": ("#c7cdd3", "#f1f4f7", "#818d99", "#ffffff"),
    "blue": ("#416d94", "#7fa3c1", "#1c3f61", "#b0d2eb"),
}


def defs(color, prefix):
    body, light, dark, edge = PALETTES[color]
    return f'''<defs>
      <linearGradient id="{prefix}body" x1="0" y1="0" x2=".9" y2="1"><stop stop-color="{light}"/><stop offset=".38" stop-color="{body}"/><stop offset="1" stop-color="{dark}"/></linearGradient>
      <linearGradient id="{prefix}metal" x1="0" y1="0" x2="1" y2="1"><stop stop-color="{edge}"/><stop offset=".28" stop-color="{body}"/><stop offset=".68" stop-color="{light}"/><stop offset="1" stop-color="{dark}"/></linearGradient>
      <linearGradient id="{prefix}screen" x1="0" y1="1" x2="1" y2="0"><stop stop-color="#071a2b"/><stop offset=".48" stop-color="#075e68"/><stop offset="1" stop-color="#63c6c0"/></linearGradient>
      <linearGradient id="{prefix}glass" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#223d4b"/><stop offset=".52" stop-color="#06111e"/><stop offset="1" stop-color="#142c3d"/></linearGradient>
      <radialGradient id="{prefix}lens"><stop stop-color="#429b9b"/><stop offset=".19" stop-color="#0a3b53"/><stop offset=".35" stop-color="#172b44"/><stop offset=".55" stop-color="#020b15"/><stop offset=".76" stop-color="#274d63"/><stop offset="1" stop-color="#080e16"/></radialGradient>
      <filter id="{prefix}shadow" x="-50%" y="-150%" width="200%" height="400%"><feGaussianBlur stdDeviation="10"/></filter>
      <pattern id="{prefix}mesh" width="7" height="7" patternUnits="userSpaceOnUse"><circle cx="2" cy="2" r="1.2" fill="#0a1119" opacity=".75"/><circle cx="5.5" cy="5.5" r=".9" fill="#d8e2eb" opacity=".22"/></pattern>
      <pattern id="{prefix}knurl" width="5" height="5" patternUnits="userSpaceOnUse"><path d="M0 0v5" stroke="#9cabb6" stroke-opacity=".3" stroke-width="2"/></pattern>
    </defs>'''


def shape(family, color, p="p"):
    body, light, dark, edge = PALETTES[color]
    g = lambda name: f"url(#{p}{name})"
    shadow = f'<ellipse cx="300" cy="424" rx="187" ry="14" fill="#152a3d" opacity=".17" filter="{g("shadow")}"/>'
    screen_art = '<path d="M131 278c86-100 132-136 246-170-26 79-99 121-116 211H131Z" fill="#69d2c7" opacity=".3"/><path d="M252 319c5-85 103-110 144-224h77v224Z" fill="#98e1df" opacity=".27"/><path d="M132 164c119 38 129 111 244 155H132Z" fill="#011a30" opacity=".5"/>'
    if family == "laptop":
        keys = ''.join(f'<rect x="{140+x*26}" y="{344+y*11}" width="21" height="7" rx="1.5" fill="#18212b" stroke="#a2adb9" stroke-opacity=".2"/>' for y in range(4) for x in range(12))
        return shadow + f'''<g transform="rotate(-3 300 255)">
          <rect x="109" y="80" width="382" height="257" rx="13" fill="{g('metal')}"/>
          <rect x="114" y="84" width="372" height="248" rx="10" fill="#101b27"/>
          <rect x="126" y="96" width="348" height="224" rx="3" fill="{g('screen')}"/>{screen_art}
          <circle cx="300" cy="89" r="2" fill="#577080"/>
          <path d="M108 334h384l70 68c-3 12-13 16-26 17H60c-13-1-22-7-23-17Z" fill="{g('metal')}"/>
          <path d="m112 338-64 62h503l-65-62Z" fill="{light}"/>
          <g transform="matrix(1 0 .25 1 -90 0)">{keys}</g>
          <path d="M257 386h86l12 17H246Z" fill="{body}" stroke="{dark}" stroke-opacity=".4"/>
          <path d="M38 403h523" stroke="{edge}" stroke-width="2"/>
          <path d="M264 405h72l-5 4h-62Z" fill="{dark}" opacity=".7"/>
          <path d="M79 413h38m365 0h36" stroke="{dark}" stroke-width="2" opacity=".55"/>
        </g>'''
    if family in ("phone", "tablet"):
        if family == "phone":
            return shadow + f'''<g transform="rotate(12 355 255)">
              <rect x="300" y="72" width="157" height="340" rx="27" fill="{g('metal')}" stroke="{edge}" stroke-width="2"/>
              <rect x="311" y="83" width="72" height="82" rx="19" fill="{body}" stroke="{edge}" stroke-opacity=".6"/>
              <circle cx="331" cy="106" r="13" fill="#0e1821" stroke="{dark}" stroke-width="4"/><circle cx="361" cy="139" r="13" fill="#101a22" stroke="{dark}" stroke-width="4"/>
              <circle cx="332" cy="106" r="6" fill="{g('lens')}"/><circle cx="361" cy="139" r="6" fill="{g('lens')}"/><circle cx="361" cy="104" r="5" fill="#ecebdf"/>
              <path d="M456 156v46m-155-66v25" stroke="{dark}" stroke-width="3"/>
            </g><g transform="rotate(-7 248 260)">
              <rect x="154" y="67" width="166" height="354" rx="28" fill="{g('metal')}" stroke="{edge}" stroke-width="1.5"/>
              <rect x="159" y="72" width="156" height="344" rx="25" fill="#08121e"/>
              <rect x="165" y="79" width="144" height="330" rx="21" fill="{g('screen')}"/>
              <path d="M165 339c14-103 117-146 144-211v151c-50 38-78 79-89 130h-55Z" fill="#7dd7d1" opacity=".4"/>
              <path d="M165 226c42 10 87 120 144 125v58H165Z" fill="#091c38" opacity=".5"/>
              <rect x="208" y="88" width="59" height="15" rx="8" fill="#09131f"/><circle cx="257" cy="95" r="3" fill="#263e4a"/>
              <rect x="213" y="397" width="48" height="3" rx="1.5" fill="#d8f0ed" opacity=".8"/>
            </g>'''
        return shadow + f'''<g transform="rotate(-8 299 258)">
          <rect x="154" y="53" width="294" height="371" rx="21" fill="{g('metal')}" stroke="{edge}" stroke-width="2"/>
          <rect x="163" y="62" width="276" height="353" rx="15" fill="#101a24"/>
          <rect x="175" y="76" width="252" height="325" rx="6" fill="{g('screen')}"/>
          <path d="M175 318c67-56 128-206 252-241v142c-63 48-77 119-114 182H175Z" fill="#8fdfd6" opacity=".38"/>
          <path d="M175 116c50 81 63 188 252 257v28H175Z" fill="#08233e" opacity=".45"/>
          <circle cx="301" cy="69" r="2" fill="#719099"/>
          <rect x="240" y="391" width="120" height="3" rx="1.5" fill="#cee9ed" opacity=".6"/>
          <path d="M450 129v55" stroke="{dark}" stroke-width="3"/>
        </g><path d="m460 114 13 3-69 287-13-3Z" fill="{g('metal')}"/><path d="m391 401 13 3-13 12Z" fill="#c2ccd4"/>'''
    if family == "headphones":
        return shadow + f'''<g transform="rotate(-8 300 260)">
          <path d="M154 293v-74c0-105 61-161 146-161s146 56 146 161v74" stroke="{dark}" stroke-width="39" stroke-linecap="round"/>
          <path d="M153 287v-69c0-99 62-152 147-152s147 53 147 152v69" stroke="{g('metal')}" stroke-width="28" stroke-linecap="round"/>
          <path d="M169 205c6-80 55-121 131-121s126 41 131 121" stroke="{edge}" stroke-opacity=".6" stroke-width="2"/>
          <path d="M150 236v78m300-78v78" stroke="#7c8c99" stroke-width="14"/>
          <path d="M151 240v58m298-58v58" stroke="#d7dfe6" stroke-opacity=".65" stroke-width="4"/>
          <g transform="rotate(-9 166 341)"><rect x="112" y="251" width="111" height="173" rx="48" fill="#111921"/><rect x="104" y="257" width="94" height="162" rx="43" fill="{g('body')}" stroke="{edge}" stroke-opacity=".65"/><path d="M124 290v95" stroke="{edge}" stroke-opacity=".25" stroke-width="3"/><path d="M175 280v113" stroke="{dark}" stroke-opacity=".7" stroke-width="2"/></g>
          <g transform="rotate(9 432 341)"><rect x="377" y="251" width="111" height="173" rx="48" fill="#111921"/><rect x="402" y="257" width="94" height="162" rx="43" fill="{g('body')}" stroke="{edge}" stroke-opacity=".65"/><path d="M475 290v95" stroke="{edge}" stroke-opacity=".4" stroke-width="3"/><circle cx="448" cy="373" r="13" stroke="{edge}" stroke-opacity=".5"/><path d="M448 367v12m-6-6h12" stroke="{edge}" stroke-opacity=".6" stroke-width="1.5"/></g>
        </g>'''
    if family == "earbuds":
        return shadow + f'''<path d="M172 271c0-33 29-55 128-55s128 22 128 55v80c0 46-38 71-128 71s-128-25-128-71Z" fill="{g('body')}" stroke="{edge}" stroke-opacity=".4" stroke-width="2"/>
          <ellipse cx="300" cy="271" rx="128" ry="54" fill="{g('metal')}"/>
          <ellipse cx="300" cy="272" rx="110" ry="38" fill="{dark}"/>
          <ellipse cx="252" cy="275" rx="31" ry="21" fill="#0a111b"/><ellipse cx="348" cy="275" rx="31" ry="21" fill="#0a111b"/>
          <path d="M179 322c79 22 161 23 242 0" stroke="{edge}" stroke-opacity=".35"/>
          <circle cx="300" cy="365" r="3" fill="#91ead8"/>
          <g transform="rotate(-25 219 148)"><rect x="208" y="130" width="26" height="109" rx="13" fill="{g('body')}" stroke="{edge}" stroke-opacity=".4"/><ellipse cx="221" cy="125" rx="38" ry="43" fill="{g('metal')}"/><ellipse cx="193" cy="121" rx="15" ry="24" fill="#15212c"/><ellipse cx="193" cy="121" rx="9" ry="17" fill="url(#{p}mesh)"/><path d="M219 157v57" stroke="{edge}" stroke-opacity=".5" stroke-width="2"/></g>
          <g transform="rotate(27 383 137)"><rect x="365" y="122" width="26" height="107" rx="13" fill="{g('body')}" stroke="{edge}" stroke-opacity=".4"/><ellipse cx="379" cy="116" rx="38" ry="43" fill="{g('metal')}"/><ellipse cx="406" cy="113" rx="15" ry="24" fill="#15212c"/><ellipse cx="406" cy="113" rx="9" ry="17" fill="url(#{p}mesh)"/><path d="M379 148v57" stroke="{edge}" stroke-opacity=".5" stroke-width="2"/></g>'''
    if family == "speaker":
        return shadow + f'''<g transform="rotate(-7 300 276)">
          <rect x="100" y="157" width="402" height="239" rx="67" fill="{g('body')}" stroke="{edge}" stroke-width="2"/>
          <rect x="109" y="165" width="384" height="223" rx="60" fill="{g('body')}"/>
          <rect x="109" y="165" width="384" height="223" rx="60" fill="url(#{p}mesh)"/>
          <path d="M165 170c95-20 201-20 272 0" stroke="{edge}" stroke-opacity=".5" stroke-width="2"/>
          <path d="M122 218v108m361-108v108" stroke="{dark}" stroke-width="10"/>
          <rect x="238" y="222" width="123" height="82" rx="17" fill="{body}" stroke="{edge}" stroke-opacity=".5"/>
          <path d="M272 266h56m-44-14v28m33-28v28" stroke="{edge}" stroke-opacity=".8" stroke-width="4" stroke-linecap="round"/>
          <path d="M201 164h18m18 0h18m18 0h18" stroke="{edge}" stroke-width="5" stroke-linecap="round"/>
          <path d="M167 390v14m269-14v14" stroke="{dark}" stroke-width="15" stroke-linecap="round"/>
        </g>'''
    if family == "camera":
        return shadow + f'''<g transform="rotate(-5 300 278)">
          <path d="M112 191h88l25-44h105l27 44h97c22 0 36 15 36 37v143c0 24-14 38-38 38H112c-25 0-40-16-40-40V232c0-26 14-41 40-41Z" fill="{g('body')}" stroke="{edge}" stroke-opacity=".6" stroke-width="2"/>
          <path d="M91 238h398v133c0 24-14 38-38 38H112c-25 0-40-16-40-40V250Z" fill="url(#{p}mesh)" opacity=".55"/>
          <path d="M96 194h69v211h-53c-25 0-40-16-40-40V232c0-22 9-35 24-38Z" fill="{dark}"/>
          <rect x="102" y="172" width="56" height="23" rx="7" fill="#2b3540"/><path d="M105 178h50m-50 7h50" stroke="#586775" stroke-width="2"/>
          <rect x="377" y="169" width="55" height="25" rx="8" fill="{g('metal')}"/>
          <rect x="244" y="157" width="62" height="13" rx="3" fill="#15212c"/>
          <circle cx="308" cy="300" r="113" fill="#0c141e" stroke="#61717d" stroke-width="4"/>
          <circle cx="308" cy="300" r="100" fill="url(#{p}knurl)" stroke="#202b35" stroke-width="8"/>
          <circle cx="308" cy="300" r="85" fill="#0b1622" stroke="#667b87" stroke-width="3"/>
          <circle cx="308" cy="300" r="71" fill="{g('lens')}" stroke="#1b3545" stroke-width="5"/>
          <circle cx="308" cy="300" r="42" fill="#060f1d" stroke="#446077" stroke-width="2"/>
          <circle cx="286" cy="276" r="15" fill="#9ddbd5" opacity=".18"/><circle cx="331" cy="320" r="8" fill="#4b89ad" opacity=".35"/>
          <circle cx="453" cy="217" r="6" fill="#94b3a6"/>
        </g>'''
    if family == "smartwatch":
        holes=''.join(f'<rect x="286" y="{y}" width="28" height="7" rx="3.5" fill="{dark}"/>' for y in [45,62,79,391,408,425])
        return shadow + f'''<g transform="rotate(13 300 250)"><rect x="249" y="26" width="102" height="430" rx="35" fill="{g('body')}"/>{holes}
          <rect x="212" y="126" width="177" height="239" rx="48" fill="{g('metal')}" stroke="{edge}" stroke-width="2"/>
          <rect x="220" y="133" width="161" height="225" rx="42" fill="#07131e"/>
          <rect x="228" y="142" width="145" height="208" rx="34" fill="{g('glass')}"/>
          <circle cx="300" cy="238" r="49" stroke="#087b84" stroke-width="10"/><circle cx="300" cy="238" r="35" stroke="#8bdac8" stroke-width="6" stroke-dasharray="150 70" transform="rotate(-90 300 238)"/>
          <path d="M300 208v31l24 15" stroke="#eefaff" stroke-width="5" stroke-linecap="round"/>
          <circle cx="300" cy="239" r="5" fill="#f3fffe"/><path d="M278 316h44" stroke="#869dac" stroke-width="4" stroke-linecap="round"/>
          <rect x="387" y="182" width="13" height="28" rx="6" fill="{g('metal')}"/><path d="M391 233v40" stroke="{dark}" stroke-width="5" stroke-linecap="round"/>
          <path d="M236 160c13-12 34-13 41-13" stroke="#fff" stroke-opacity=".4" stroke-width="3" stroke-linecap="round"/>
        </g>'''
    if family == "keyboard":
        keys=''.join(f'<rect x="{82+x*35}" y="{177+y*37}" width="29" height="29" rx="5" fill="{light}" stroke="{dark}" stroke-opacity=".45"/><path d="M{89+x*35} {184+y*37}h7" stroke="{dark}" stroke-width="2" opacity=".6"/>' for x in range(12) for y in range(4))
        return shadow + f'''<g transform="rotate(-8 300 280)"><rect x="58" y="151" width="480" height="225" rx="17" fill="{g('metal')}" stroke="{edge}" stroke-width="2"/><rect x="67" y="161" width="462" height="200" rx="10" fill="{body}"/>{keys}
          <rect x="83" y="326" width="56" height="27" rx="4" fill="{light}"/><rect x="147" y="326" width="56" height="27" rx="4" fill="{light}"/><rect x="211" y="326" width="173" height="27" rx="4" fill="{light}"/><rect x="393" y="326" width="56" height="27" rx="4" fill="{light}"/><rect x="457" y="326" width="56" height="27" rx="4" fill="{light}"/>
          <rect x="82" y="177" width="29" height="29" rx="5" fill="#087d83"/><circle cx="505" cy="169" r="2.5" fill="#7ff2d7"/>
        </g>'''
    if family == "mouse":
        return shadow + f'''<g transform="rotate(-22 300 260)">
          <path d="M213 177c0-75 35-119 88-119s88 44 88 119l11 138c4 68-35 109-100 109s-103-41-99-109Z" fill="{g('body')}" stroke="{edge}" stroke-opacity=".7" stroke-width="2"/>
          <path d="M218 182c0-74 32-117 82-117v174H212Z" fill="{light}" opacity=".28"/>
          <path d="M300 66v175m-88 1h177" stroke="{dark}" stroke-width="3"/>
          <rect x="286" y="110" width="28" height="66" rx="14" fill="#10212c"/>
          <path d="M293 119v48m7-49v50m7-49v48" stroke="#607b89" stroke-width="2"/>
          <path d="M220 285v53m8-54v57" stroke="{edge}" stroke-opacity=".4" stroke-width="3" stroke-linecap="round"/>
          <path d="M240 391c31 13 73 14 106 0" stroke="{edge}" stroke-opacity=".4" stroke-width="2"/>
        </g>'''
    if family == "charger":
        return shadow + f'''<path d="M358 281c135-18 138 119 6 133-95 10-171 27-188-35-9-34 48-57 101-33" stroke="#b7c2cd" stroke-width="12" fill="none"/>
          <path d="M358 281c135-18 138 119 6 133-95 10-171 27-188-35-9-34 48-57 101-33" stroke="#eef2f5" stroke-width="6" fill="none"/>
          <g transform="rotate(-13 288 221)"><path d="M234 115V75m72 40V75" stroke="#8494a1" stroke-width="16"/><path d="M231 77h6m66 0h6" stroke="#f0f4f5" stroke-width="4"/>
          <rect x="187" y="113" width="183" height="207" rx="28" fill="{g('metal')}" stroke="{edge}" stroke-width="2"/>
          <path d="M204 122h113c18 0 27 8 27 26v149H216c-12 0-20-9-20-20V137c0-10 3-15 8-15Z" fill="{light}" opacity=".35"/>
          <rect x="342" y="193" width="16" height="54" rx="5" fill="#26343e"/><rect x="347" y="201" width="6" height="38" rx="3" fill="#99afb9"/>
          <path d="M230 259h52" stroke="{dark}" stroke-width="2" opacity=".4"/><path d="M230 269h35" stroke="{dark}" stroke-width="2" opacity=".3"/>
          </g><g transform="rotate(22 313 349)"><rect x="277" y="335" width="56" height="25" rx="9" fill="#d9e1e7"/><rect x="323" y="340" width="21" height="15" rx="3" fill="#6b8495"/></g>'''
    if family == "screwdriver":
        bits=''.join(f'<g transform="translate({x} {y})"><rect x="0" y="0" width="12" height="44" rx="2" fill="#a5b2bd"/><path d="M3 0V-14h6V0" fill="#8295a4"/><path d="M3 5v31" stroke="#ecf2f6" stroke-width="2"/></g>' for x,y in [(388,275),(425,262),(463,250)])
        return shadow + f'''<g transform="rotate(35 260 254)">
          <rect x="232" y="66" width="34" height="114" rx="4" fill="{g('metal')}"/><path d="M240 70V39h18v31" fill="#8b9baa"/><path d="M242 46h14" stroke="#e5edf2" stroke-width="3"/>
          <rect x="207" y="164" width="84" height="246" rx="36" fill="{g('body')}" stroke="{edge}" stroke-width="2"/>
          <rect x="217" y="192" width="64" height="121" rx="20" fill="{dark}" opacity=".75"/>
          <path d="M226 204v95m10-96v101m11-102v102m11-101v101m11-99v97" stroke="{edge}" stroke-opacity=".22" stroke-width="3"/>
          <rect x="235" y="332" width="28" height="48" rx="14" fill="#0c1c28"/><circle cx="249" cy="346" r="5" fill="#5bbcb2"/>
          <path d="M215 177h68" stroke="{edge}" stroke-width="3"/>
        </g>{bits}'''
    if family == "hub":
        return shadow + f'''<path d="M212 173c-100-36-147-6-138 48 7 42 41 49 73 19" stroke="#4c606e" stroke-width="13" fill="none"/>
          <path d="M212 173c-100-36-147-6-138 48 7 42 41 49 73 19" stroke="#879ba7" stroke-width="4" fill="none"/>
          <g transform="rotate(-17 318 280)">
          <rect x="155" y="170" width="338" height="179" rx="26" fill="{g('metal')}" stroke="{edge}" stroke-width="2"/>
          <rect x="155" y="188" width="338" height="161" rx="23" fill="{g('body')}"/>
          <path d="M160 196h327" stroke="{edge}" stroke-opacity=".7"/>
          <rect x="193" y="252" width="57" height="24" rx="3" fill="#172a38"/><rect x="199" y="258" width="45" height="12" fill="#195c87"/>
          <rect x="269" y="252" width="57" height="24" rx="3" fill="#172a38"/><rect x="275" y="258" width="45" height="12" fill="#195c87"/>
          <rect x="350" y="251" width="37" height="13" rx="6.5" fill="#172a38"/><path d="M409 253h49l-5 23h-40Z" fill="#172a38"/>
          <circle cx="452" cy="188" r="3" fill="#92f3d5"/>
          </g><g transform="rotate(-38 154 213)"><rect x="125" y="197" width="64" height="30" rx="9" fill="{g('body')}"/><rect x="180" y="204" width="24" height="17" rx="5" fill="#c9d4dc" stroke="#667f90" stroke-width="2"/></g>'''
    if family == "smart-camera":
        return shadow + f'''<ellipse cx="300" cy="410" rx="112" ry="23" fill="{g('metal')}" stroke="{edge}" stroke-opacity=".6"/>
          <path d="M261 322h78l17 84c-31 12-81 12-112 0Z" fill="{g('body')}"/>
          <path d="M204 252c-18-104 7-175 96-175s114 71 96 175c-8 61-36 89-96 89s-88-28-96-89Z" fill="{g('metal')}" stroke="{edge}" stroke-width="2"/>
          <ellipse cx="300" cy="212" rx="77" ry="96" fill="#14212d"/><ellipse cx="300" cy="212" rx="66" ry="84" fill="{g('glass')}"/>
          <circle cx="300" cy="200" r="43" fill="#040c15" stroke="#758e9d" stroke-width="4"/>
          <circle cx="300" cy="200" r="31" fill="{g('lens')}"/>
          <circle cx="289" cy="188" r="8" fill="#7fc8d8" opacity=".23"/>
          <circle cx="300" cy="274" r="4" fill="#61c8b4"/><path d="M283 308h34" stroke="{dark}" stroke-width="3" stroke-linecap="round"/>
          <path d="M238 128c13-18 29-27 43-29" stroke="{edge}" stroke-opacity=".6" stroke-width="3" stroke-linecap="round"/>'''
    raise ValueError(family)


def render(family, color):
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 500" fill="none" role="img" aria-label="{color.title()} {family.replace("-", " ")}">{defs(color,"p")}{shape(family,color)}</svg>\n'


def hero():
    pieces = [
        ("headphones", "black", "h", "translate(12 95) scale(.53) rotate(-8 300 250)"),
        ("laptop", "silver", "l", "translate(145 95) scale(.88)"),
        ("phone", "blue", "m", "translate(580 200) scale(.48) rotate(8 300 250)"),
    ]
    art=''.join(defs(color, p) + f'<g transform="{transform}">{shape(family,color,p)}</g>' for family,color,p,transform in pieces)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 620" fill="none" role="img" aria-label="Laptop, headphones and mobile phone on a cool studio desk">
      <defs><linearGradient id="back" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#e4f2f0"/><stop offset=".65" stop-color="#eff4f4"/><stop offset="1" stop-color="#d3e5e3"/></linearGradient><radialGradient id="glow"><stop stop-color="#fff" stop-opacity=".8"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></radialGradient></defs>
      <path d="M0 0h900v620H0Z" fill="url(#back)"/><ellipse cx="420" cy="240" rx="390" ry="280" fill="url(#glow)"/>
      <path d="M0 427 900 396v224H0Z" fill="#c6d8d6" opacity=".45"/><path d="m0 427 900-31" stroke="#bfd0cf" stroke-width="2"/>
      {art}
    </svg>\n'''


if __name__ == "__main__":
    DEST.mkdir(parents=True, exist_ok=True)
    families=("laptop","tablet","headphones","earbuds","speaker","camera","smartwatch","phone","keyboard","mouse","charger","screwdriver","hub","smart-camera")
    for family in families:
        for color in PALETTES:
            (DEST / f"{family}-{color}.svg").write_text(render(family,color),encoding="utf-8")
    (DEST / "hero.svg").write_text(hero(),encoding="utf-8")
    print(f"Generated {len(families) * len(PALETTES)} product variants and one hero in {DEST}")
