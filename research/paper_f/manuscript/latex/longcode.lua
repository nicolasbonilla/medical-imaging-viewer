-- LaTeX only: let long inline code (hashes, digests, paths) break anywhere, so tables do not overflow.
local BS = string.char(92)  -- backslash

local function escape(s)
  s = s:gsub(BS, BS .. 'textbackslash{}')
  s = s:gsub('([_%%#&{}%$])', BS .. '%1')
  s = s:gsub('~', BS .. 'textasciitilde{}')
  s = s:gsub('%^', BS .. 'textasciicircum{}')
  return s
end

function Code(el)
  if FORMAT:match('latex') and #el.text > 22 then
    return pandoc.RawInline('latex', BS .. 'texttt{' .. BS .. 'seqsplit{' .. escape(el.text) .. '}}')
  end
end
