#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "PollingUDPReceiver.generated.h"

class FSocket;

UCLASS()
class TEST_UNREAL_API APollingUDPReceiver : public AActor
{
    GENERATED_BODY()
    
public:    
    APollingUDPReceiver();

    // The port number to listen on. This is editable in the editor.
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "UDP Polling Receiver")
    int32 ListenPort = 25565;

    // This is the function that our child Blueprint will implement.
    UFUNCTION(BlueprintImplementableEvent, Category = "UDP Polling Receiver")
    void OnDataReceived(const FString& Data);

protected:
    virtual void BeginPlay() override;
    virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;

public:    
    // Called every frame
    virtual void Tick(float DeltaTime) override;

private:
    // The network socket.
    FSocket* ListenSocket;

    // A reusable buffer for incoming data.
    TArray<uint8> ReceiveBuffer;
};
