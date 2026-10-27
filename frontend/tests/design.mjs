/** Dependency-free CSS design contract for the warm Frost system.
 * Runtime pixel/blur verification still requires a real Safari/Chromium UI. */
import {readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {dirname,resolve} from 'node:path';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'..','dist');
const load=p=>readFileSync(resolve(root,p),'utf8');
const system=load('assets/css/system.css');
const layout=load('assets/css/layout.css');
const components=load('assets/css/components.css');
const main=load('assets/js/main.js');
const views=load('assets/js/views.js');
const checks=[
  ['pure-white light canvas',/--bg:\s*#ffffff\s*;/.test(system)],
  ['orange accent token',/--accent:\s*#f88c45\s*;/.test(system)],
  ['graphite CTA token',/--graphite:\s*#252422\s*;/.test(system)],
  ['no original purple tokens',!/#5264e8|#6575ef|#495bdc|rgba\(82,100,232/.test(system+layout+components)],
  ['single shared radius for capsule buttons',/\.btn\s*\{[^}]*border-radius:\s*var\(--r-pill\)/s.test(components)],
  ['compact buttons stay capsules',/\.btn-sm\s*\{[^}]*border-radius:\s*var\(--r-pill\)/s.test(components)],
  ['nested cards inherit smaller radius',/\.card\.inset,\s*\.card \.card\.inset\s*\{[^}]*border-radius:\s*var\(--nested-radius\)/s.test(components)],
  ['inset metrics use nested radius',/\.metric\s*\{[^}]*border-radius:\s*var\(--nested-radius\)/s.test(components)],
  ['material has strong rim top and weak sides',/--glass-rim:\s*linear-gradient\(180deg/.test(system)],
  ['large orange arc renders on homepage only',
    main.includes("container.classList.toggle('is-home',path==='/')") &&
    /#app\.is-home::before\s*\{[^}]*position:\s*fixed/s.test(layout) &&
    /#app\.is-home::before\s*\{[^}]*background:\s*linear-gradient\(/s.test(layout) &&
    /background:\s*linear-gradient\(125deg,\s*var\(--accent\)\s+0%,\s*var\(--accent-strong\)\s+100%\)/.test(layout) &&
    /mask-image:.*data:image\/svg\+xml/.test(layout) &&
    /pointer-events:\s*none/.test(layout)],
  ['landing tiles share the full main shell',/\.hero\s*\{[^}]*width:\s*100%/s.test(layout) && /\.hero-actions\s*\{[^}]*grid-template-columns:\s*repeat\(2,minmax\(0,1fr\)\)/s.test(layout)],
  ['header capsule surrounds the edge actions',/\.topbar\s*\{[^}]*border-radius:\s*var\(--r-pill\)/s.test(layout) && /@media \(max-width:720px\)[\s\S]*?\.topbar\s*\{[^}]*border-radius:\s*var\(--r-pill\)/s.test(layout)],
  ['demo marker is next to brand text',views.includes("<span class=\"brand-word\">Clinical Compass</span>${demo?") && views.includes("<span class=\"brand-demo\">Демо</span>")],
  ['reference link is grouped with login on the right',!views.includes('class="header-center"') && views.includes('<div class="header-right"><a class="btn btn-quiet header-library" href="/#/clinical-library">Справочник</a>${menu}</div>') && /\.header-right\s*\{[^}]*margin-left:\s*auto/s.test(layout)],
  ['reference link has the same type as login',views.includes('btn btn-quiet header-library') && views.includes('btn btn-quiet" href="/#/login')],
  ['responsive reference link',/\.header-library\s*\{\s*display:\s*none/.test(layout)],
  ['homepage role cards are informational',views.includes("roleTile('Исследователю'") && /\.role-tile\s*\{[^}]*min-height/.test(components)],
  ['Frost for cards',/\.glass,\s*\.card,\s*\.action-tile,\s*\.glass-panel\s*\{[^}]*backdrop-filter:\s*var\(--frost\)/s.test(components)],
  ['Frost for dropdown',/\.account-menu\s*\{[^}]*backdrop-filter:\s*var\(--frost-dense\)/s.test(layout)],
  ['Frost for dialog',/\.dialog\s*\{[^}]*backdrop-filter:\s*var\(--frost-dense\)/s.test(components)],
  ['all-behind blur for overlays',/\.overlay\s*\{[^}]*backdrop-filter:\s*var\(--overlay-blur\)/s.test(components)],
  ['account menu in independent portal',main.includes("byid('floating-root')") && main.includes('menuToggle')],
  ['graphite panel from reference',views.includes("'graphite-feature'")],
  ['both themes retain a Frost surface',/\:root\[data-theme="dark"\][\s\S]*?--glass-fill:/.test(system)],
  ['single rim lies directly on outer edge',
    /@supports \(\(-webkit-mask-composite: xor\) or \(mask-composite: exclude\)\)/.test(components) &&
    /border-width:\s*0;/.test(components) &&
    /::after\s*\{[\s\S]*?inset:\s*0;/.test(components)],
  ['hover cannot remove or fade the gradient border',
    !/hover::after\s*\{/.test(components) &&
    !/\.btn-secondary:hover\s*\{[^}]*border-color/.test(components)],
  ['cards remain completely static on hover',
    !/:is\(\.glass, \.card, \.action-tile, \.glass-panel\):hover/.test(components) &&
    !/\.card:hover/.test(components) &&
    !/\.action-tile:hover/.test(components) &&
    !/\.glass-panel:hover/.test(components) &&
    !/\.graphite-feature:hover/.test(components) &&
    !/\.card, \.action-tile, \.glass-panel, \.glass\s*\{[^}]*transition:/.test(components) &&
    !/\.action-tile\s*\{[^}]*transition:/.test(components)],
  ['neutral secondary button hover',
    /\.btn-secondary:hover\s*\{[^}]*background:\s*var\(--glass-hover-raised\)/.test(components)],
  ['no duplicate inner white strokes on glass',
    !/--glass-shadow:[^;]*inset/.test(system) &&
    !/--shadow-float:[^;]*inset/.test(system) &&
    !/--shadow-inset:[^;]*inset/.test(system) &&
    !/--control-shadow:[^;]*inset/.test(system) &&
    !/\.btn-secondary\s*\{[^}]*box-shadow:\s*inset/.test(components)],
  ['missing-backdrop fallback',system.includes('@supports not ((backdrop-filter:')],
];
for(const [name,pass] of checks){console.log(`${pass?'PASS':'FAIL'} - ${name}`);if(!pass)process.exitCode=1;}
