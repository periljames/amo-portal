from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def replace_once(rel: str, old: str, new: str) -> None:
    path = ROOT / rel
    content = path.read_text(encoding="utf-8")
    count = content.count(old)
    if count != 1:
        raise RuntimeError(f"Expected one match in {rel}, found {count}: {old[:120]!r}")
    path.write_text(content.replace(old, new, 1), encoding="utf-8")


# React lint does not permit constructing JSX inside the QR encoder try/catch.
# Compute primitive coordinates under the exception boundary and render JSX after it.
replace_once(
    "frontend/src/pages/PublicCarInvitePage.tsx",
    '''const InviteQr: React.FC<{ value: string }> = ({ value }) => {\n  const qr = useMemo(() => {\n    try {\n      const matrix = new QRCodeWriter().encode(value, BarcodeFormat.QR_CODE, 180, 180) as {\n        get: (x: number, y: number) => boolean;\n        getWidth: () => number;\n        getHeight: () => number;\n      };\n      const width = matrix.getWidth();\n      const height = matrix.getHeight();\n      const cells: React.ReactNode[] = [];\n      for (let y = 0; y < height; y += 1) {\n        for (let x = 0; x < width; x += 1) {\n          if (matrix.get(x, y)) cells.push(<rect key={`${x}-${y}`} x={x} y={y} width="1" height="1" />);\n        }\n      }\n      return { width, height, cells };\n    } catch {\n      return null;\n    }\n  }, [value]);\n\n  if (!qr) return <a href={value} className="car-invite-btn">Open on phone</a>;\n\n  return (\n    <svg className="car-invite-qr" viewBox={`0 0 ${qr.width} ${qr.height}`} role="img" aria-label="QR code for phone capture">\n      <rect width={qr.width} height={qr.height} fill="white" />\n      <g fill="black">{qr.cells}</g>\n    </svg>\n  );\n};\n''',
    '''const InviteQr: React.FC<{ value: string }> = ({ value }) => {\n  const qr = useMemo(() => {\n    try {\n      const matrix = new QRCodeWriter().encode(value, BarcodeFormat.QR_CODE, 180, 180) as {\n        get: (x: number, y: number) => boolean;\n        getWidth: () => number;\n        getHeight: () => number;\n      };\n      const width = matrix.getWidth();\n      const height = matrix.getHeight();\n      const cells: Array<{ x: number; y: number }> = [];\n      for (let y = 0; y < height; y += 1) {\n        for (let x = 0; x < width; x += 1) {\n          if (matrix.get(x, y)) cells.push({ x, y });\n        }\n      }\n      return { width, height, cells };\n    } catch {\n      return null;\n    }\n  }, [value]);\n\n  if (!qr) return <a href={value} className="car-invite-btn">Open on phone</a>;\n\n  return (\n    <svg className="car-invite-qr" viewBox={`0 0 ${qr.width} ${qr.height}`} role="img" aria-label="QR code for phone capture">\n      <rect width={qr.width} height={qr.height} fill="white" />\n      <g fill="black">{qr.cells.map((cell) => <rect key={`${cell.x}-${cell.y}`} x={cell.x} y={cell.y} width="1" height="1" />)}</g>\n    </svg>\n  );\n};\n''',
)

# Keep the new response list stable for memoized latest-response selection.
replace_once(
    "frontend/src/pages/qms/QmsCarControlOperations.tsx",
    '  const responses = responsesQuery.data ?? [];\n  const attachments = attachmentsQuery.data ?? [];\n',
    '  const responses = useMemo(() => responsesQuery.data ?? [], [responsesQuery.data]);\n  const attachments = attachmentsQuery.data ?? [];\n',
)

# Do not claim a deletion audit event that the existing attachment endpoint does not guarantee.
replace_once(
    "frontend/src/pages/qms/QmsCarControlOperations.tsx",
    '    if (!window.confirm(`Remove evidence file ${attachment.filename}? The action remains attributable in the CAR history.`)) return;\n',
    '    if (!window.confirm(`Remove evidence file ${attachment.filename} from the current CAR evidence set?`)) return;\n',
)

# Opening a print window with noopener can yield a null WindowProxy in some browsers.
replace_once(
    "frontend/src/pages/qms/QmsCarControlOperations.tsx",
    '    const popup = window.open("", "_blank", "noopener,noreferrer,width=1100,height=850");\n',
    '    const popup = window.open("", "_blank", "width=1100,height=850");\n',
)
replace_once(
    "frontend/src/pages/qms/QmsCarControlOperations.tsx",
    '    const response = latestResponse || source;\n',
    '    popup.opener = null;\n    const response = latestResponse || source;\n',
)

print("CAR frontend lint/hardening follow-up applied")
