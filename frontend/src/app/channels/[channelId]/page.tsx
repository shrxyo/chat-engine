import { MessageList } from '@/components/messages/MessageList'

interface ChannelPageProps {
  params: Promise<{ channelId: string }>
}

export default async function ChannelPage({ params }: ChannelPageProps) {
  const { channelId } = await params

  return (
    <MessageList
      channelId={channelId}
      channelName={channelId}
    />
  )
}
