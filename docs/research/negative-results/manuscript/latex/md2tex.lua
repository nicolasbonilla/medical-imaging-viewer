-- md2tex.lua — pandoc Lua filter used by build_latex.py to put a reviewed manuscript.md into a
-- journal LaTeX template WITHOUT changing its text.
--
-- * headings: the hand-written numbers ("3.1", "1.", "Appendix A —") are removed and LaTeX numbers
--   the sections; where LaTeX would give a different number, a \setcounter forces the written one,
--   so every number in the text stays valid.  Unnumbered headings become \section* etc.
-- * tables: "**Table N. ...**" paragraphs become the caption of the table that follows, with the
--   written label N (labels in these manuscripts are not always in order of appearance); notes that
--   follow a table (a paragraph starting with a superscript marker) go into the float. Tables are set
--   with tabulary (column widths from the content) in \footnotesize, so nothing overflows.
-- * figures: "Figure N." is taken from the caption (or from the file name figN_*.png when the caption
--   has none), the vector PDF next to the PNG is used, at its native size (never scaled).
-- * long inline code (hashes, paths) may break anywhere (seqsplit).
--
-- Parameters come in as metadata: mt_twocol ("true"/"false"), mt_colwidth, mt_textwidth (pt),
-- mt_figsizes (path of a JSON file {name: [w_pt, h_pt]}), mt_figprefix (path prefix for figures),
-- mt_shortcols (max characters of a table row that still fits one column).

local BS = string.char(92)
local twocol = false
local colwidth = 0
local textwidth = 0
local textheight = 0
local figsizes = {}
local figprefix = ''
local shortcols = 60
local appendix_started = false
local shift = 0   -- heading-level shift (mt_shift), applied here so the counters see the final levels
local counters = {0, 0, 0, 0, 0, 0}
local cnames = {'section', 'subsection', 'subsubsection', 'paragraph', 'subparagraph', 'subparagraph'}

local function blk(blocks)
  -- the command line's writer options, so that citations inside tables and captions become natbib commands
  local s = pandoc.write(pandoc.Pandoc(blocks), 'latex', PANDOC_WRITER_OPTIONS)
  -- not '%s': in some C locales %s also matches byte 0xA0, the last byte of UTF-8 characters such as the dagger
  return (s:gsub('[ \t\r\n]+$', ''))
end

local function inl(inlines)
  return blk({pandoc.Plain(inlines)})
end

local function escape(s)
  s = s:gsub(BS, BS .. 'textbackslash{}')
  s = s:gsub('([_%%#&{}%$])', BS .. '%1')
  s = s:gsub('~', BS .. 'textasciitilde{}')
  s = s:gsub('%^', BS .. 'textasciicircum{}')
  return s
end

-- ---------------------------------------------------------------- metadata
local function read_meta(m)
  if m.mt_twocol then twocol = pandoc.utils.stringify(m.mt_twocol) == 'true' end
  if m.mt_colwidth then colwidth = tonumber(pandoc.utils.stringify(m.mt_colwidth)) end
  if m.mt_textwidth then textwidth = tonumber(pandoc.utils.stringify(m.mt_textwidth)) end
  if m.mt_textheight then textheight = tonumber(pandoc.utils.stringify(m.mt_textheight)) end
  if m.mt_figprefix then figprefix = pandoc.utils.stringify(m.mt_figprefix) end
  if m.mt_shortcols then shortcols = tonumber(pandoc.utils.stringify(m.mt_shortcols)) end
  if m.mt_figsizes then
    local f = io.open(pandoc.utils.stringify(m.mt_figsizes), 'r')
    if f then
      figsizes = pandoc.json.decode(f:read('a'))
      f:close()
    end
  end
  if m.mt_appendix_started then appendix_started = pandoc.utils.stringify(m.mt_appendix_started) == 'true' end
  if m.mt_shift then shift = tonumber(pandoc.utils.stringify(m.mt_shift)) end
end

-- ---------------------------------------------------------------- inline code
-- seqsplit works byte by byte and drops spaces: only runs of printable ASCII without spaces go inside it;
-- spaces and other characters stay outside (a space becomes an ordinary inter-word space)
local function splittable(text)
  local out, run = {}, {}
  local function flush()
    if #run > 0 then
      table.insert(out, BS .. 'seqsplit{' .. escape(table.concat(run)) .. '}')
      run = {}
    end
  end
  for _, cp in utf8.codes(text) do
    if cp == 32 then
      flush()
      table.insert(out, ' ')
    elseif cp < 128 then
      table.insert(run, utf8.char(cp))
    else
      flush()
      table.insert(out, utf8.char(cp))
    end
  end
  flush()
  return table.concat(out)
end

-- long words without break points (hashes, identifiers) in running text may break anywhere
local function Str(el)
  local n = utf8.len(el.text)
  if n and n > (twocol and 16 or 24) and el.text:match('^%(?[%w%.%-_/:#=+]+[%.,;:%)]*$') and el.text:match('[%d/_]') then
    return pandoc.RawInline('latex', splittable(el.text))
  end
  -- "PRB/CAPA", "open_ms_data": a line may break after a slash or an underscore
  if (el.text:find('/', 1, true) or el.text:find('_', 1, true)) and n and n > 6 and not el.text:find('://', 1, true) then
    local s = escape(el.text)
    s = s:gsub('/', '/' .. BS .. 'allowbreak{}')
    s = s:gsub(BS .. '_', BS .. '_' .. BS .. 'allowbreak{}')
    return pandoc.RawInline('latex', s)
  end
end

local function Code(el)
  if #el.text > (twocol and 8 or 12) then
    return pandoc.RawInline('latex', BS .. 'texttt{' .. splittable(el.text) .. '}')
  end
end

-- ---------------------------------------------------------------- headings
local function split_num(s)
  local parts = {}
  for p in s:gmatch('%d+') do table.insert(parts, tonumber(p)) end
  return parts
end

local function Header(h)
  h.level = math.max(1, h.level + shift)
  local c = h.content
  local pre = {}
  local first = c[1]
  if first and first.t == 'Str' and first.text:match('^%d+[%.%d]*%.?$') then
    local parts = split_num(first.text)
    -- drop number and the following space
    local rest = pandoc.Inlines({})
    for i = 3, #c do rest:insert(c[i]) end
    if #c >= 2 and c[2].t ~= 'Space' then
      rest = pandoc.Inlines({})
      for i = 2, #c do rest:insert(c[i]) end
    end
    h.content = rest
    local L = h.level
    if #parts ~= L then
      io.stderr:write('md2tex: heading number ' .. first.text .. ' has ' .. #parts .. ' parts at level ' .. L .. string.char(10))
    end
    for k = 1, L - 1 do
      if parts[k] and parts[k] ~= counters[k] then
        table.insert(pre, pandoc.RawBlock('latex', BS .. 'setcounter{' .. cnames[k] .. '}{' .. parts[k] .. '}'))
        counters[k] = parts[k]
      end
    end
    local want = parts[L] or (counters[L] + 1)
    if want ~= counters[L] + 1 then
      table.insert(pre, pandoc.RawBlock('latex', BS .. 'setcounter{' .. cnames[L] .. '}{' .. (want - 1) .. '}'))
    end
    counters[L] = want
    for k = L + 1, #counters do counters[k] = 0 end
    h.classes = h.classes:filter(function(x) return x ~= 'unnumbered' end)
  elseif first and first.t == 'Str' and first.text == 'Appendix' then
    local letter = c[3] and c[3].t == 'Str' and c[3].text:match('^([A-Z])[%.:]?$')
    if not appendix_started then
      table.insert(pre, pandoc.RawBlock('latex', BS .. 'appendix'))
      appendix_started = true
      counters[1] = 0
    end
    if letter then
      local i = 4
      while c[i] and (c[i].t == 'Space' or (c[i].t == 'Str' and (c[i].text == '—' or c[i].text == '–' or c[i].text == ':' or c[i].text == '-'))) do i = i + 1 end
      local rest = pandoc.Inlines({})
      for j = i, #c do rest:insert(c[j]) end
      h.content = rest
      local expected = string.char(64 + counters[1] + 1)
      if counters[1] >= 0 and letter ~= expected then
        table.insert(pre, pandoc.RawBlock('latex', BS .. 'setcounter{section}{' .. (string.byte(letter) - 65) .. '}'))
      end
      counters[1] = string.byte(letter) - 64
      for k = 2, #counters do counters[k] = 0 end
    else
      h.classes:insert('unnumbered')
    end
  else
    if not h.classes:includes('unnumbered') then h.classes:insert('unnumbered') end
  end
  h.identifier = ''
  if #pre > 0 then
    table.insert(pre, h)
    return pre
  end
  return h
end

-- ---------------------------------------------------------------- tables
local function starts_label(inlines, word)
  -- returns label, number of inlines consumed (Str word, Space, Str label.)
  if #inlines >= 3 and inlines[1].t == 'Str' and inlines[1].text == word and inlines[2].t == 'Space'
     and inlines[3].t == 'Str' then
    local lab = inlines[3].text:match('^([A-Z]?%d+[a-z]?)%.$')
    if lab then return lab end
  end
  return nil
end

local function drop_first(inlines, n)
  local out = pandoc.Inlines({})
  for i = n + 1, #inlines do out:insert(inlines[i]) end
  while #out > 0 and (out[1].t == 'Space' or out[1].t == 'SoftBreak') do out:remove(1) end
  return out
end

-- caption paragraph: returns label, caption inlines
local function table_caption(b, word)
  if b.t ~= 'Para' then return nil end
  local c = b.content
  if c[1] and c[1].t == 'Strong' then
    local lab = starts_label(c[1].content, word)
    if lab then
      local inner = drop_first(c[1].content, 3)
      local rest = drop_first(c, 1)
      local cap = pandoc.Inlines({})
      local spaced = c[2] and (c[2].t == 'Space' or c[2].t == 'SoftBreak')
      if #inner > 0 then cap:insert(pandoc.Strong(inner)); if #rest > 0 and spaced then cap:insert(pandoc.Space()) end end
      cap:extend(rest)
      return lab, cap
    end
  end
  local lab = starts_label(c, word)
  if lab then return lab, drop_first(c, 3) end
  return nil
end

local function is_note(b)
  if b.t ~= 'Para' then return false end
  local f = b.content[1]
  if not f then return false end
  if f.t == 'Superscript' then return true end
  if f.t == 'Str' then
    local first = pandoc.text.sub(f.text, 1, 1)
    local SUP = 'ᵃᵇᶜᵈᵉᶠᵍʰⁱʲᵏˡᵐⁿᵒᵖʳˢᵗᵘᵛʷˣʸᶻ'
    if utf8.len(first) == 1 and SUP:find(first, 1, true) then return true end
    if f.text == 'Note:' or f.text == 'Notes:' or f.text == 'Note.' or f.text == 'Notes.' then return true end
  end
  if f.t == 'Emph' then
    local s = pandoc.utils.stringify(f)
    if s:match('^Notes?[%.:]') or s == 'Note' or s == 'Notes' then return true end
  end
  return false
end

local function cell_text(cell)
  local s = blk(cell.contents)
  s = s:gsub('\n\n+', BS .. 'newline{}'):gsub('\n', ' ')
  return s
end

local function row_cells(row)
  local out = {}
  -- \hspace{0pt}: TeX never hyphenates the first word of a paragraph; this lets narrow cells hyphenate it
  for _, cell in ipairs(row.cells) do table.insert(out, BS .. 'hspace{0pt}' .. cell_text(cell)) end
  return out
end

local function plain_len(row)
  local n = 0
  for _, cell in ipairs(row.cells) do n = n + utf8.len(pandoc.utils.stringify(cell.contents)) + 3 end
  return n
end

-- column widths from content (for tables that must break across pages, where tabulary cannot be used)
local function col_weights(t)
  local ncol = #t.colspecs
  local mx = {}
  for i = 1, ncol do mx[i] = 4 end
  local function scan(r)
    for i, cell in ipairs(r.cells) do
      local l = utf8.len(pandoc.utils.stringify(cell.contents)) or 0
      if l > mx[i] then mx[i] = l end
    end
  end
  for _, r in ipairs(t.head.rows) do scan(r) end
  for _, body in ipairs(t.bodies) do for _, r in ipairs(body.body) do scan(r) end end
  local w, sum = {}, 0
  for i = 1, ncol do w[i] = math.min(mx[i], 70) ^ 0.75; sum = sum + w[i] end
  for i = 1, ncol do w[i] = w[i] / sum end
  return w, mx
end

-- rough height of the table set at width_pt in \footnotesize (about 4.4 pt per character, 9.5 pt per line)
local function est_height(t, width_pt)
  local w = col_weights(t)
  local ncol = #t.colspecs
  local usable = width_pt - ncol * 12
  local h = 0
  local function rowh(r)
    local lines = 1
    for i, cell in ipairs(r.cells) do
      local l = utf8.len(pandoc.utils.stringify(cell.contents)) or 0
      local per = math.max(4, math.floor(usable * w[i] / 4.4))
      lines = math.max(lines, math.ceil(l / per))
    end
    return lines * 9.5 + 2
  end
  for _, r in ipairs(t.head.rows) do h = h + rowh(r) end
  for _, body in ipairs(t.bodies) do for _, r in ipairs(body.body) do h = h + rowh(r) end end
  return h + 40
end

local function make_longtable(t, lab, cap, notes)
  local w = col_weights(t)
  local ncol = #t.colspecs
  local spec = {}
  for i = 1, ncol do
    table.insert(spec, '>{' .. BS .. 'raggedright' .. BS .. 'arraybackslash}p{' ..
      string.format('%.3f', w[i]) .. '\\dimexpr' .. BS .. 'textwidth-' .. (2 * ncol) .. BS .. 'tabcolsep' .. BS .. 'relax}')
  end
  local head = {}
  for _, r in ipairs(t.head.rows) do table.insert(head, table.concat(row_cells(r), ' & ') .. ' ' .. BS .. BS) end
  local out = {}
  if twocol then table.insert(out, BS .. 'onecolumn') end
  table.insert(out, BS .. 'begingroup' .. BS .. 'footnotesize')
  if lab then table.insert(out, BS .. 'renewcommand{' .. BS .. 'thetable}{' .. lab .. '}%mtlabel') end
  table.insert(out, BS .. 'begin{longtable}{@{}' .. table.concat(spec) .. '@{}}%mtcolspec')
  if lab then table.insert(out, BS .. 'caption[]{' .. inl(cap) .. '}' .. BS .. BS) end
  table.insert(out, BS .. 'toprule')
  for _, h in ipairs(head) do table.insert(out, h) end
  table.insert(out, BS .. 'midrule' .. BS .. 'endfirsthead')
  table.insert(out, '%mtrepeat-begin')
  table.insert(out, BS .. 'mtcontinued{' .. ncol .. '}' .. BS .. BS)
  table.insert(out, BS .. 'toprule')
  for _, h in ipairs(head) do table.insert(out, h) end
  table.insert(out, BS .. 'midrule' .. BS .. 'endhead')
  table.insert(out, '%mtrepeat-end')
  table.insert(out, BS .. 'bottomrule' .. BS .. 'endlastfoot')
  for _, body in ipairs(t.bodies) do
    for _, r in ipairs(body.body) do table.insert(out, table.concat(row_cells(r), ' & ') .. ' ' .. BS .. BS) end
  end
  table.insert(out, BS .. 'end{longtable}')
  if #notes > 0 then
    table.insert(out, BS .. 'par' .. BS .. 'raggedright')
    for _, nb in ipairs(notes) do table.insert(out, blk({nb}) .. BS .. 'par') end
  end
  table.insert(out, BS .. 'endgroup')
  if twocol then table.insert(out, BS .. 'twocolumn') end
  io.stderr:write('md2tex: table ' .. (lab or '(no caption)') .. ' is taller than a page: set as a longtable' ..
    (twocol and ' on one-column pages' or '') .. string.char(10))
  return pandoc.RawBlock('latex', table.concat(out, '\n'))
end

local function make_table(t, lab, cap, notes)
  local ncol = #t.colspecs
  local align = {}
  for i, cs in ipairs(t.colspecs) do
    local a = cs[1]
    if a == 'AlignRight' then align[i] = 'R' elseif a == 'AlignCenter' then align[i] = 'C' else align[i] = 'L' end
  end
  local maxlen = 0
  local rows = {}
  for _, r in ipairs(t.head.rows) do maxlen = math.max(maxlen, plain_len(r)) end
  for _, body in ipairs(t.bodies) do for _, r in ipairs(body.body) do maxlen = math.max(maxlen, plain_len(r)) end end
  local wide = twocol and maxlen > shortcols
  if textheight > 0 and est_height(t, wide and textwidth or (twocol and colwidth or textwidth)) > 0.9 * textheight then
    return make_longtable(t, lab, cap, notes)
  end
  local env = wide and 'table*' or 'table'
  local width = wide and (BS .. 'textwidth') or (BS .. 'columnwidth')
  local out = {}
  table.insert(out, BS .. 'begin{' .. env .. '}[' .. (wide and 'tp' or 'tbp') .. ']')
  table.insert(out, BS .. 'centering' .. BS .. 'footnotesize')
  if lab then
    table.insert(out, BS .. 'renewcommand{' .. BS .. 'thetable}{' .. lab .. '}%mtlabel')
    table.insert(out, BS .. 'caption[]{' .. inl(cap) .. '}')
  end
  table.insert(out, BS .. 'begin{tabulary}{' .. width .. '}{@{}' .. table.concat(align) .. '@{}}')
  table.insert(out, BS .. 'toprule')
  for _, r in ipairs(t.head.rows) do table.insert(out, table.concat(row_cells(r), ' & ') .. ' ' .. BS .. BS) end
  table.insert(out, BS .. 'midrule')
  for _, body in ipairs(t.bodies) do
    for _, r in ipairs(body.body) do table.insert(out, table.concat(row_cells(r), ' & ') .. ' ' .. BS .. BS) end
  end
  table.insert(out, BS .. 'bottomrule')
  table.insert(out, BS .. 'end{tabulary}')
  if #notes > 0 then
    table.insert(out, BS .. 'par' .. BS .. 'smallskip' .. BS .. 'raggedright')
    for _, nb in ipairs(notes) do table.insert(out, blk({nb}) .. BS .. 'par') end
  end
  table.insert(out, BS .. 'end{' .. env .. '}')
  return pandoc.RawBlock('latex', table.concat(out, '\n'))
end

-- ---------------------------------------------------------------- figures
local function make_figure(fig)
  local img = nil
  fig.content:walk({Image = function(i) img = i end})
  if not img then return nil end
  local cap = pandoc.Inlines({})
  for _, blk in ipairs(fig.caption.long) do
    if blk.content then cap:extend(blk.content) end
  end
  local lab = nil
  local auto = false
  if cap[1] and cap[1].t == 'Strong' then
    lab = starts_label(cap[1].content, 'Figure')
    if lab then
      local inner = drop_first(cap[1].content, 3)
      local rest = drop_first(cap, 1)
      local spaced = cap[2] and (cap[2].t == 'Space' or cap[2].t == 'SoftBreak')
      cap = pandoc.Inlines({})
      if #inner > 0 then cap:insert(pandoc.Strong(inner)); if #rest > 0 and spaced then cap:insert(pandoc.Space()) end end
      cap:extend(rest)
    end
  end
  if not lab then
    lab = starts_label(cap, 'Figure')
    if lab then cap = drop_first(cap, 3) end
  end
  local src = img.src
  local base = src:match('([^/\\]+)$')
  local stem = base:gsub('%.%w+$', '')
  if not lab then
    lab = stem:match('^fig(%d+)')
    auto = true
  end
  local fname = stem .. '.pdf'
  local size = figsizes[fname]
  if not size then
    fname = base
    size = figsizes[base]
  end
  local w = size and size[1] or 0
  local env = 'figure'
  if twocol and w > colwidth + 0.5 then env = 'figure*' end
  local inc = BS .. 'includegraphics{' .. figprefix .. fname .. '}'
  local limit = (env == 'figure*' or not twocol) and textwidth or colwidth
  if w > limit + 0.5 then
    inc = BS .. 'makebox[' .. BS .. 'linewidth][c]{' .. inc .. '}'
    io.stderr:write(string.format('md2tex: figure %s is %.0f pt wide, wider than %.0f pt: set at native size, centred\n', fname, w, limit))
  end
  local out = {}
  table.insert(out, BS .. 'begin{' .. env .. '}[' .. (env == 'figure*' and 'tp' or 'tbp') .. ']')
  table.insert(out, BS .. 'centering')
  table.insert(out, inc)
  table.insert(out, BS .. 'renewcommand{' .. BS .. 'thefigure}{' .. lab .. '}%' .. (auto and 'mtautolabel' or 'mtlabel'))
  table.insert(out, BS .. 'caption[]{' .. inl(cap) .. '}')
  table.insert(out, BS .. 'end{' .. env .. '}')
  return pandoc.RawBlock('latex', table.concat(out, '\n'))
end

-- ---------------------------------------------------------------- block sequences
local function Blocks(blocks)
  local out = pandoc.Blocks({})
  local i = 1
  while i <= #blocks do
    local b = blocks[i]
    if b.t == 'Table' then
      local lab, cap = nil, nil
      local j = #out
      while j >= 1 and out[j].t == 'RawBlock' and out[j].format == 'html' do j = j - 1 end
      if j >= 1 then
        local l, c = table_caption(out[j], 'Table')
        if l then lab, cap = l, c; out:remove(j) end
      end
      local notes = {}
      local k = i + 1
      while k <= #blocks and blocks[k].t == 'RawBlock' and blocks[k].format == 'html' do k = k + 1 end
      while k <= #blocks and is_note(blocks[k]) do table.insert(notes, blocks[k]); k = k + 1 end
      if k == i + 1 then k = i + 1 end
      out:insert(make_table(b, lab, cap, notes))
      i = (#notes > 0) and k or (i + 1)
    elseif b.t == 'Figure' then
      local f = make_figure(b)
      out:insert(f or b)
      i = i + 1
    else
      out:insert(b)
      i = i + 1
    end
  end
  return out
end

local function CodeBlock(cb)
  -- fvextra: long command lines wrap instead of running into the margin
  return pandoc.RawBlock('latex', BS .. 'begin{Verbatim}[fontsize=' .. BS .. 'footnotesize,breaklines,breakanywhere]\n' .. cb.text .. '\n' .. BS .. 'end{Verbatim}')
end

return {
  {Meta = read_meta},
  {Str = Str, Code = Code, CodeBlock = CodeBlock},
  {Header = Header},
  {Blocks = Blocks},
}
