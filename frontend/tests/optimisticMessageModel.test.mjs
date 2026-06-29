import test from 'node:test'
import assert from 'node:assert/strict'

async function loadModel() {
  try {
    return await import('../src/features/relay/optimisticMessageModel.ts')
  } catch (error) {
    throw new assert.AssertionError({
      message: `expected optimistic message model to exist: ${error.message}`,
    })
  }
}

test('optimistic messages append immediately and stay scoped to one conversation', async () => {
  const {
    addOptimisticMessage,
    getOptimisticMessagesForConversation,
  } = await loadModel()

  let buckets = {}
  buckets = addOptimisticMessage(buckets, 101, '  first task  ', () => 'p1')
  buckets = addOptimisticMessage(buckets, 202, 'other thread', () => 'p2')
  buckets = addOptimisticMessage(buckets, 101, '\nfollow-up\n', () => 'p3')
  buckets = addOptimisticMessage(buckets, 101, '   ', () => 'p4')

  assert.deepEqual(getOptimisticMessagesForConversation(buckets, 101), [
    { id: 'p1', text: 'first task' },
    { id: 'p3', text: 'follow-up' },
  ])
  assert.deepEqual(getOptimisticMessagesForConversation(buckets, 202), [
    { id: 'p2', text: 'other thread' },
  ])
})

test('removing an optimistic message clears only that pending card', async () => {
  const {
    addOptimisticMessage,
    getOptimisticMessagesForConversation,
    removeOptimisticMessage,
  } = await loadModel()

  let buckets = {}
  buckets = addOptimisticMessage(buckets, 101, 'first task', () => 'p1')
  buckets = addOptimisticMessage(buckets, 101, 'second task', () => 'p2')
  buckets = addOptimisticMessage(buckets, 202, 'other thread', () => 'p3')

  buckets = removeOptimisticMessage(buckets, 101, 'p1')

  assert.deepEqual(getOptimisticMessagesForConversation(buckets, 101), [
    { id: 'p2', text: 'second task' },
  ])
  assert.deepEqual(getOptimisticMessagesForConversation(buckets, 202), [
    { id: 'p3', text: 'other thread' },
  ])

  buckets = removeOptimisticMessage(buckets, 101, 'p2')
  assert.deepEqual(getOptimisticMessagesForConversation(buckets, 101), [])
})
