import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const __dirname = dirname(fileURLToPath(import.meta.url))
const threadViewSource = readFileSync(join(__dirname, '../src/components/ThreadView.tsx'), 'utf8')

test('ThreadView does not synthesize waiting status copy in the message stream', () => {
  const forbiddenCopy = [
    'Sending trigger to ChatGPT',
    'Waiting for the agent to call back',
    'Waiting for callback events',
    'Trigger state:',
  ]

  for (const copy of forbiddenCopy) {
    assert.equal(
      threadViewSource.includes(copy),
      false,
      `ThreadView should not render "${copy}" as message-stream status text`,
    )
  }
})
