interface ChannelPageProps {
  params: Promise<{ channelId: string }>
}

export default async function ChannelPage({ params }: ChannelPageProps) {
  const { channelId } = await params

  return (
    <main className="flex min-h-screen flex-col">
      <h1 className="p-4 text-xl font-semibold">Channel: {channelId}</h1>
    </main>
  )
}
