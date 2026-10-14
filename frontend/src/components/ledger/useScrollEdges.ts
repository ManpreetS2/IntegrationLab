import { useEffect, useState } from 'react'

export function useScrollEdges(node: HTMLElement | null, watch: unknown) {
  const [edges, setEdges] = useState({ left: false, right: false })

  useEffect(() => {
    if (!node) return
    const update = () => {
      setEdges({
        left: node.scrollLeft > 4,
        right: node.scrollLeft + node.clientWidth < node.scrollWidth - 4,
      })
    }
    update()
    node.addEventListener('scroll', update, { passive: true })
    const observer = new ResizeObserver(update)
    observer.observe(node)
    return () => {
      node.removeEventListener('scroll', update)
      observer.disconnect()
    }
  }, [node, watch])

  return edges
}
