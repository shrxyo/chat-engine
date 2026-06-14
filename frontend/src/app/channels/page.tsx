/**
 * Index route for /channels (no channel selected).
 *
 * The actual empty-state UI ("Select a channel to start chatting.") is rendered
 * by ChannelShell in the layout when no channelId is present, so this page only
 * needs to exist to make /channels a routable segment.
 */
export default function ChannelsIndexPage() {
  return null
}
