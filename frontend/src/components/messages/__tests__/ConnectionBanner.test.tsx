import { afterEach, describe, expect, it } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { ConnectionBanner } from '../ConnectionBanner'

describe('ConnectionBanner', () => {
  afterEach(cleanup)

  it('renders nothing while connected and caught up', () => {
    const { container } = render(<ConnectionBanner isReconnecting={false} isCatchingUp={false} />)
    expect(container.innerHTML).toBe('')
  })

  it('shows reconnecting while the socket is down', () => {
    render(<ConnectionBanner isReconnecting isCatchingUp={false} />)
    expect(screen.getByRole('status').textContent).toBe('Reconnecting…')
  })

  it('shows catching up after the socket is back', () => {
    render(<ConnectionBanner isReconnecting={false} isCatchingUp />)
    expect(screen.getByRole('status').textContent).toBe('Reconnected — catching up…')
  })
})
