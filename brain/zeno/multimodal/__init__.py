"""The multimodal layer: sight (VLM) and voice (STT/TTS) on queue-fed worker tasks.

The EventBus carries small typed facts; bounded asyncio queues carry the work; native
models run on one dedicated thread per worker. See ZENO_MULTIMODAL_ARCH.md.
"""
