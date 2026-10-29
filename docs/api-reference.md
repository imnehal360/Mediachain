# API reference

## Main client and shared models

::: mediachain.MediaChain
    options:
      members: true

::: mediachain.ProcessingConfig

::: mediachain.MediaAsset

::: mediachain.ModelResponse

::: mediachain.RetrievalFilter

::: mediachain.SourceReference

## Loaders

::: mediachain.loaders.LocalLoader

::: mediachain.loaders.HTTPSLoader

## Processors

::: mediachain.processors.TextProcessor

::: mediachain.processors.AudioProcessor

::: mediachain.processors.VideoProcessor

## Embeddings and models

::: mediachain.embeddings.HashEmbeddings

::: mediachain.embeddings.SentenceTransformerEmbeddings

::: mediachain.models.HTTPChatModel

::: mediachain.models.HTTPVisionModel

::: mediachain.models.HTTPSpeechModel

::: mediachain.models.HTTPDiarizationModel

::: mediachain.models.HTTPEmbeddingModel

::: mediachain.models.FasterWhisperSpeech

## Storage

::: mediachain.storage.SQLiteStore

::: mediachain.storage.MemoryVectorStore

::: mediachain.storage.PostgresStore

::: mediachain.storage.QdrantVectorStore

::: mediachain.storage.RedisCache

::: mediachain.storage.S3ObjectStore

::: mediachain.processors.VisionPDFOCR

## Agents

::: mediachain.agents.Agent

::: mediachain.agents.AgentLimits

::: mediachain.agents.AgentRun

::: mediachain.agents.media_tools

## Application API

The REST endpoint and persistent-conversation overview is in the
[web application guide](web-application.md). The running server generates its request/response
schemas at `/docs`. The Python `MediaChain.ask` API is stateless; conversation persistence and
bounded follow-up context are provided by the conversation REST endpoints.
