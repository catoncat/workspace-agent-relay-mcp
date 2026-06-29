import test from 'node:test'
import assert from 'node:assert/strict'

import {
  appendQueuedMessage,
  editQueuedMessage,
  getQueuedMessagesForConversation,
  mergeQueuedMessages,
  removeQueuedMessage,
  takeQueuedMessage,
  updateQueuedMessagesForConversation,
} from '../src/features/relay/queueModel.ts'

test('queued messages append in FIFO order and ignore blank input', () => {
  const first = appendQueuedMessage([], '  first  ', () => 'q1')
  const second = appendQueuedMessage(first, '\nsecond\n', () => 'q2')
  const blank = appendQueuedMessage(second, '   ', () => 'q3')

  assert.deepEqual(blank, [
    { id: 'q1', text: 'first' },
    { id: 'q2', text: 'second' },
  ])
})

test('queued messages can be edited or removed without reordering remaining items', () => {
  const queue = [
    { id: 'q1', text: 'first' },
    { id: 'q2', text: 'second' },
    { id: 'q3', text: 'third' },
  ]

  assert.deepEqual(editQueuedMessage(queue, 'q2', ' updated second '), [
    { id: 'q1', text: 'first' },
    { id: 'q2', text: 'updated second' },
    { id: 'q3', text: 'third' },
  ])

  assert.deepEqual(removeQueuedMessage(queue, 'q2'), [
    { id: 'q1', text: 'first' },
    { id: 'q3', text: 'third' },
  ])
})

test('taking one queued message removes only that item for immediate guidance', () => {
  const queue = [
    { id: 'q1', text: 'first' },
    { id: 'q2', text: 'second' },
    { id: 'q3', text: 'third' },
  ]

  assert.deepEqual(takeQueuedMessage(queue, 'q2'), {
    message: { id: 'q2', text: 'second' },
    queue: [
      { id: 'q1', text: 'first' },
      { id: 'q3', text: 'third' },
    ],
  })
})

test('flushing queued messages merges visible rows into one backend message in FIFO order', () => {
  const queue = [
    { id: 'q1', text: 'first' },
    { id: 'q2', text: 'second' },
    { id: 'q3', text: 'third' },
  ]

  assert.equal(mergeQueuedMessages(queue), 'first\n\nsecond\n\nthird')
})

test('queued messages are isolated by conversation bucket', () => {
  let buckets = {}
  buckets = updateQueuedMessagesForConversation(buckets, 101, (queue) =>
    appendQueuedMessage(queue, 'first conversation', () => 'a1'),
  )
  buckets = updateQueuedMessagesForConversation(buckets, 202, (queue) =>
    appendQueuedMessage(queue, 'second conversation', () => 'b1'),
  )

  assert.deepEqual(getQueuedMessagesForConversation(buckets, 101), [
    { id: 'a1', text: 'first conversation' },
  ])
  assert.deepEqual(getQueuedMessagesForConversation(buckets, 202), [
    { id: 'b1', text: 'second conversation' },
  ])

  buckets = updateQueuedMessagesForConversation(buckets, 101, (queue) =>
    removeQueuedMessage(queue, 'a1'),
  )

  assert.deepEqual(getQueuedMessagesForConversation(buckets, 101), [])
  assert.deepEqual(getQueuedMessagesForConversation(buckets, 202), [
    { id: 'b1', text: 'second conversation' },
  ])
})
