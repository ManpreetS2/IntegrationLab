/** Labeled design fixtures. Not live provider evidence. */

export const FIXTURE = {
  notice:
    'Design fixture. These rows illustrate hierarchy only. They are not live GitHub or Stripe deliveries.',
  summary:
    'One integration needs attention. Stripe Billing Sandbox has two events in the failed queue. GitHub is not connected.',
  support:
    'Health uses stored evidence only. Failure Lab simulations do not change provider health.',
  metrics: [
    { label: 'Healthy', value: '0', tone: 'ok' as const },
    { label: 'Degraded', value: '1', tone: 'warn' as const },
    { label: 'Failed', value: '0', tone: 'danger' as const },
    { label: 'Unknown', value: '0', tone: 'neutral' as const },
  ],
  attention: {
    provider: 'Stripe',
    name: 'Stripe Billing Sandbox',
    state: 'Degraded',
    line: '2 events in the failed queue · 2 duplicate deliveries absorbed',
    action: 'Inspect failed events',
  },
  integrations: [
    {
      id: 'gh',
      provider: 'GitHub',
      name: 'GitHub Developer Integration',
      state: 'Not configured',
      tone: 'neutral' as const,
      detail: 'No OAuth credential is in use. Connect GitHub before any real request evidence exists.',
    },
    {
      id: 'st',
      provider: 'Stripe',
      name: 'Stripe Billing Sandbox',
      state: 'Degraded',
      tone: 'warn' as const,
      detail:
        '6 signature-verified events in the fixture window. 4 processed, 2 failed (webhook_invalid_event_data).',
    },
    {
      id: 'ci',
      provider: 'GitHub',
      name: 'CI Smoke GitHub',
      state: 'Not configured',
      tone: 'neutral' as const,
      detail: 'Placeholder integration. Not connected.',
    },
  ],
  activity: [
    {
      kind: 'Synthetic webhook',
      title: 'payment_intent.succeeded',
      meta: 'pi_ui_showcase_usd_2400 · processed · locally signed fixture',
    },
    {
      kind: 'Simulated',
      title: 'GET /user · HTTP 429',
      meta: 'Failure Lab · github_rate_limited · not a live GitHub call',
    },
    {
      kind: 'Diagnostic',
      title: 'Stripe checks · warning',
      meta: 'Failed queue needs attention · secret value not shown',
    },
  ],
}
