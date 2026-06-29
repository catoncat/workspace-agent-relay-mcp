import {
  Outlet,
  createRootRouteWithContext,
  createRoute,
  createRouter,
} from '@tanstack/react-router'
import type { QueryClient } from '@tanstack/react-query'
import { RelayPage } from '@/pages/RelayPage'
import {
  bootstrapOptions,
  queryClient,
  runDetailOptions,
  runsOptions,
} from '@/lib/queryClient'

interface RouterContext {
  queryClient: QueryClient
}

const rootRoute = createRootRouteWithContext<RouterContext>()({
  // Prime the bootstrap cache so an authenticated refresh renders without a
  // waterfall. Swallow rejections so an unauthenticated first run still renders
  // the shell (the user can then enter a token in Settings).
  loader: ({ context }) =>
    context.queryClient.ensureQueryData(bootstrapOptions).catch(() => undefined),
  component: () => <Outlet />,
})

const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/',
  component: RelayPage,
})

const conversationRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/c/$conversationId',
  component: RelayPage,
  loader: async ({ context, params }) => {
    const conversationId = Number(params.conversationId)
    if (!Number.isFinite(conversationId)) return
    await context.queryClient
      .ensureQueryData(runsOptions(conversationId))
      .catch(() => undefined)
  },
})

const runRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/c/$conversationId/r/$runId',
  component: RelayPage,
  loader: async ({ context, params }) => {
    const conversationId = Number(params.conversationId)
    const runId = Number(params.runId)
    if (Number.isFinite(conversationId)) {
      await context.queryClient
        .ensureQueryData(runsOptions(conversationId))
        .catch(() => undefined)
    }
    if (Number.isFinite(runId)) {
      await context.queryClient
        .ensureQueryData(runDetailOptions(runId))
        .catch(() => undefined)
    }
  },
})

const routeTree = rootRoute.addChildren([indexRoute, conversationRoute, runRoute])

export const router = createRouter({
  routeTree,
  context: { queryClient },
  defaultPreloadStaleTime: 0,
})

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router
  }
}
