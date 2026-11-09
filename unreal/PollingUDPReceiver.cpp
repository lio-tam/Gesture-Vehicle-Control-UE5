#include "PollingUDPReceiver.h"
#include "Networking.h"
#include "Sockets.h"
#include "SocketSubsystem.h"

APollingUDPReceiver::APollingUDPReceiver()
{
    // Set this actor to call Tick() every frame. This is essential for our polling logic.
    PrimaryActorTick.bCanEverTick = true;
    PrimaryActorTick.bStartWithTickEnabled = true;

    ListenSocket = nullptr;
}

void APollingUDPReceiver::BeginPlay()
{
    Super::BeginPlay();

    // Create the socket
    FIPv4Endpoint Endpoint(FIPv4Address::Any, ListenPort);
    ListenSocket = FUdpSocketBuilder(TEXT("PollingListenSocket"))
        .AsNonBlocking()
        .AsReusable()
        .BoundToEndpoint(Endpoint)
        .WithReceiveBufferSize(2 * 1024 * 1024); // 2 MB buffer

    if (ListenSocket)
    {
        UE_LOG(LogTemp, Log, TEXT("PollingUDPReceiver: Socket created and listening on port %d"), ListenPort);
    }
    else
    {
        UE_LOG(LogTemp, Error, TEXT("PollingUDPReceiver: Failed to create socket on port %d"), ListenPort);
    }
}

void APollingUDPReceiver::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
    Super::EndPlay(EndPlayReason);

    if (ListenSocket)
    {
        ListenSocket->Close();
        ISocketSubsystem::Get(PLATFORM_SOCKETSUBSYSTEM)->DestroySocket(ListenSocket);
        ListenSocket = nullptr;
        UE_LOG(LogTemp, Log, TEXT("PollingUDPReceiver: Socket closed."));
    }
}

void APollingUDPReceiver::Tick(float DeltaTime)
{
    Super::Tick(DeltaTime);

    // If the socket is not valid, there's nothing to do.
    if (!ListenSocket)
    {
        return;
    }

    // Check if there is any data pending on the socket.
    uint32 Size;
    while (ListenSocket->HasPendingData(Size))
    {
        // Resize our buffer to the pending data size.
        ReceiveBuffer.SetNumUninitialized(FMath::Min(Size, 65507u));

        int32 Read = 0;
        // Create an FInternetAddr object to store the sender's address.
        // This is the correct type required by the RecvFrom function.
        TSharedRef<FInternetAddr> Sender = ISocketSubsystem::Get(PLATFORM_SOCKETSUBSYSTEM)->CreateInternetAddr();

        // Read the data from the socket.
        if (ListenSocket->RecvFrom(ReceiveBuffer.GetData(), ReceiveBuffer.Num(), Read, *Sender))
        {
            // Make sure we read some data.
            if (Read > 0)
            {
                // Add a null terminator to the buffer to create a valid C-style string.
                ReceiveBuffer.SetNum(Read + 1);
                ReceiveBuffer[Read] = 0;

                // Convert the byte array to an FString.
                const FString ReceivedString = FString(UTF8_TO_TCHAR(ReceiveBuffer.GetData()));

                // UE_LOG(LogTemp, Warning, TEXT("PollingUDPReceiver: Received data from %s: %s"), *Sender->ToString(true), *ReceivedString);

                // Directly call the BlueprintImplementableEvent. This is safe because Tick() is on the game thread.
                OnDataReceived(ReceivedString);
            }
        }
    }
}