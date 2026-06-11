const escapeHtml = (value: string) =>
  value
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;')

const renderInlineMarkdown = (value: string) => {
  const escaped = escapeHtml(value)
  return escaped
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
}

const wrapList = (tag: 'ul' | 'ol', items: string[]) => {
  return `<${tag}>${items.map((item) => `<li>${item}</li>`).join('')}</${tag}>`
}

export const renderMarkdownToHtml = (source: string) => {
  const normalized = source.replaceAll('\r\n', '\n').trim()
  if (!normalized) {
    return ''
  }

  const blocks: string[] = []
  const lines = normalized.split('\n')
  let paragraphLines: string[] = []
  let unorderedItems: string[] = []
  let orderedItems: string[] = []

  const flushParagraph = () => {
    if (paragraphLines.length === 0) {
      return
    }
    blocks.push(`<p>${paragraphLines.join('<br />')}</p>`)
    paragraphLines = []
  }

  const flushUnordered = () => {
    if (unorderedItems.length === 0) {
      return
    }
    blocks.push(wrapList('ul', unorderedItems))
    unorderedItems = []
  }

  const flushOrdered = () => {
    if (orderedItems.length === 0) {
      return
    }
    blocks.push(wrapList('ol', orderedItems))
    orderedItems = []
  }

  const flushAll = () => {
    flushParagraph()
    flushUnordered()
    flushOrdered()
  }

  for (const rawLine of lines) {
    const line = rawLine.trimEnd()
    if (!line.trim()) {
      flushAll()
      continue
    }

    const headingMatch = line.match(/^(#{1,4})\s+(.*)$/)
    if (headingMatch) {
      flushAll()
      const level = Math.min(headingMatch[1].length, 4)
      blocks.push(`<h${level}>${renderInlineMarkdown(headingMatch[2].trim())}</h${level}>`)
      continue
    }

    const unorderedMatch = line.match(/^\s*[-*]\s+(.*)$/)
    if (unorderedMatch) {
      flushParagraph()
      flushOrdered()
      unorderedItems.push(renderInlineMarkdown(unorderedMatch[1].trim()))
      continue
    }

    const orderedMatch = line.match(/^\s*\d+\.\s+(.*)$/)
    if (orderedMatch) {
      flushParagraph()
      flushUnordered()
      orderedItems.push(renderInlineMarkdown(orderedMatch[1].trim()))
      continue
    }

    flushUnordered()
    flushOrdered()
    paragraphLines.push(renderInlineMarkdown(line.trim()))
  }

  flushAll()
  return blocks.join('')
}
