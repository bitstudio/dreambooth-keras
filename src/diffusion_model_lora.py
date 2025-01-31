# Copyright 2022 The KerasCV Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import tensorflow as tf
from tensorflow import keras
from keras_cv.models.stable_diffusion import DiffusionModel
from keras_cv.models.stable_diffusion.__internal__.layers.padded_conv2d import (
    PaddedConv2D,
)

from src.lora import LoraInjectedLinearWrapper


class LoRADiffusionModel(keras.Model):
    def __init__(
        self,
        img_height,
        img_width,
        max_text_length,
        name=None,
        download_weights=True,
    ):
        context = keras.layers.Input((max_text_length, 768))
        t_embed_input = keras.layers.Input((320,))
        latent = keras.layers.Input((img_height // 8, img_width // 8, 4))

        t_emb = keras.layers.Dense(1280)(t_embed_input)
        t_emb = keras.layers.Activation("swish")(t_emb)
        t_emb = keras.layers.Dense(1280)(t_emb)

        # Downsampling flow

        outputs = []
        x = PaddedConv2D(320, kernel_size=3, padding=1)(latent)
        outputs.append(x)

        for _ in range(2):
            x = ResBlock(320)([x, t_emb])
            x = SpatialTransformer(8, 40, fully_connected=False)([x, context])
            outputs.append(x)
        x = PaddedConv2D(320, 3, strides=2, padding=1)(x)  # Downsample 2x
        outputs.append(x)

        for _ in range(2):
            x = ResBlock(640)([x, t_emb])
            x = SpatialTransformer(8, 80, fully_connected=False)([x, context])
            outputs.append(x)
        x = PaddedConv2D(640, 3, strides=2, padding=1)(x)  # Downsample 2x
        outputs.append(x)

        for _ in range(2):
            x = ResBlock(1280)([x, t_emb])
            x = SpatialTransformer(8, 160, fully_connected=False)([x, context])
            outputs.append(x)
        x = PaddedConv2D(1280, 3, strides=2, padding=1)(x)  # Downsample 2x
        outputs.append(x)

        for _ in range(2):
            x = ResBlock(1280)([x, t_emb])
            outputs.append(x)

        # Middle flow

        x = ResBlock(1280)([x, t_emb])
        x = SpatialTransformer(8, 160, fully_connected=False)([x, context])
        x = ResBlock(1280)([x, t_emb])

        # Upsampling flow

        for _ in range(3):
            x = keras.layers.Concatenate()([x, outputs.pop()])
            x = ResBlock(1280)([x, t_emb])
        x = Upsample(1280)(x)

        for _ in range(3):
            x = keras.layers.Concatenate()([x, outputs.pop()])
            x = ResBlock(1280)([x, t_emb])
            x = SpatialTransformer(8, 160, fully_connected=False)([x, context])
        x = Upsample(1280)(x)

        for _ in range(3):
            x = keras.layers.Concatenate()([x, outputs.pop()])
            x = ResBlock(640)([x, t_emb])
            x = SpatialTransformer(8, 80, fully_connected=False)([x, context])
        x = Upsample(640)(x)

        for _ in range(3):
            x = keras.layers.Concatenate()([x, outputs.pop()])
            x = ResBlock(320)([x, t_emb])
            x = SpatialTransformer(8, 40, fully_connected=False)([x, context])

        # Exit flow

        x = keras.layers.GroupNormalization(epsilon=1e-5)(x)
        x = keras.layers.Activation("swish")(x)
        output = PaddedConv2D(4, kernel_size=3, padding=1)(x)

        super().__init__([latent, t_embed_input, context], output, name=name)

        self.prepare_training_layers()
        self._trainable_variables = self.get_trainable_variables()

        if download_weights:
            cpus = tf.config.list_logical_devices("CPU")

            with tf.device(cpus[0]):
                _diffusion_model = DiffusionModel(
                    img_height,
                    img_width,
                    max_text_length,
                    download_weights=True,
                )
                self.import_weights(_diffusion_model)

            del _diffusion_model

    def prepare_training_layers(self):
        for i in range(len(self.layers)):
            if self.layers[i].name.find("spatial_transformer") == -1:
                self.layers[i].trainable = False

    def import_weights(self, diffusion_model):
        for i in range(len(self.layers)):
            lora_l = self.layers[i]
            ori_l = diffusion_model.layers[i]
            lora_w = lora_l.get_weights()
            ori_w = ori_l.get_weights()
            if lora_l.name.find("spatial_transformer") != -1:
                lora_w[16:] = ori_w
                self.layers[i].set_weights(lora_w)
            else:
                self.layers[i].set_weights(ori_w)

    def get_trainable_variables(self):
        trainable_vars = []
        for i in range(len(self.layers)):
            t_variables = self.layers[i].trainable_variables
            trainable_vars += t_variables
        return trainable_vars


class ResBlock(keras.layers.Layer):
    def __init__(self, output_dim, **kwargs):
        super().__init__(**kwargs)
        self.output_dim = output_dim
        self.entry_flow = [
            keras.layers.GroupNormalization(epsilon=1e-5),
            keras.layers.Activation("swish"),
            PaddedConv2D(output_dim, 3, padding=1),
        ]
        self.embedding_flow = [
            keras.layers.Activation("swish"),
            keras.layers.Dense(output_dim),
        ]
        self.exit_flow = [
            keras.layers.GroupNormalization(epsilon=1e-5),
            keras.layers.Activation("swish"),
            PaddedConv2D(output_dim, 3, padding=1),
        ]

    def build(self, input_shape):
        if input_shape[0][-1] != self.output_dim:
            self.residual_projection = PaddedConv2D(self.output_dim, 1)

        else:
            self.residual_projection = lambda x: x

    def call(self, inputs):
        inputs, embeddings = inputs
        x = inputs
        for layer in self.entry_flow:
            x = layer(x)
        for layer in self.embedding_flow:
            embeddings = layer(embeddings)
        x = x + embeddings[:, None, None]
        for layer in self.exit_flow:
            x = layer(x)
        return x + self.residual_projection(inputs)


class SpatialTransformer(keras.layers.Layer):
    def __init__(self, num_heads, head_size, fully_connected=False, **kwargs):
        super().__init__(**kwargs)
        self.norm = keras.layers.GroupNormalization(epsilon=1e-5)
        self.norm.trainable = False
        channels = num_heads * head_size
        if fully_connected:
            self.proj1 = keras.layers.Dense(num_heads * head_size)
        else:
            self.proj1 = PaddedConv2D(num_heads * head_size, 1)
        self.proj1.trainable = False
        self.transformer_block = BasicTransformerBlock(channels, num_heads, head_size)
        if fully_connected:
            self.proj2 = keras.layers.Dense(channels)
        else:
            self.proj2 = PaddedConv2D(channels, 1)
        self.proj2.trainable = False

    def call(self, inputs):
        inputs, context = inputs
        _, h, w, c = inputs.shape
        x = self.norm(inputs)
        x = self.proj1(x)
        x = tf.reshape(x, (-1, h * w, c))
        x = self.transformer_block([x, context])
        x = tf.reshape(x, (-1, h, w, c))
        return self.proj2(x) + inputs


class BasicTransformerBlock(keras.layers.Layer):
    def __init__(self, dim, num_heads, head_size, **kwargs):
        super().__init__(**kwargs)
        self.norm1 = keras.layers.LayerNormalization(epsilon=1e-5)
        self.attn1 = CrossAttention(num_heads, head_size)
        self.norm2 = keras.layers.LayerNormalization(epsilon=1e-5)
        self.attn2 = CrossAttention(num_heads, head_size)
        self.norm3 = keras.layers.LayerNormalization(epsilon=1e-5)
        self.geglu = GEGLU(dim * 4)
        self.dense = keras.layers.Dense(dim)

        self.norm1.trainable = False
        self.norm2.trainable = False
        self.norm3.trainable = False
        self.dense.trainable = False

    def call(self, inputs):
        inputs, context = inputs
        x = self.attn1([self.norm1(inputs), None]) + inputs
        x = self.attn2([self.norm2(x), context]) + x
        return self.dense(self.geglu(self.norm3(x))) + x


class CrossAttention(keras.layers.Layer):
    def __init__(self, num_heads, head_size, **kwargs):
        super().__init__(**kwargs)
        self.to_q = LoraInjectedLinearWrapper(
            keras.layers.Dense(num_heads * head_size, use_bias=False)
        )
        self.to_k = LoraInjectedLinearWrapper(
            keras.layers.Dense(num_heads * head_size, use_bias=False)
        )
        self.to_v = LoraInjectedLinearWrapper(
            keras.layers.Dense(num_heads * head_size, use_bias=False)
        )
        self.scale = head_size**-0.5
        self.num_heads = num_heads
        self.head_size = head_size
        self.out_proj = LoraInjectedLinearWrapper(
            keras.layers.Dense(num_heads * head_size)
        )

    def call(self, inputs):
        inputs, context = inputs
        context = inputs if context is None else context
        q, k, v = self.to_q(inputs), self.to_k(context), self.to_v(context)
        q = tf.reshape(q, (-1, inputs.shape[1], self.num_heads, self.head_size))
        k = tf.reshape(k, (-1, context.shape[1], self.num_heads, self.head_size))
        v = tf.reshape(v, (-1, context.shape[1], self.num_heads, self.head_size))

        q = tf.transpose(q, (0, 2, 1, 3))  # (bs, num_heads, time, head_size)
        k = tf.transpose(k, (0, 2, 3, 1))  # (bs, num_heads, head_size, time)
        v = tf.transpose(v, (0, 2, 1, 3))  # (bs, num_heads, time, head_size)

        score = td_dot(q, k) * self.scale
        weights = keras.activations.softmax(score)  # (bs, num_heads, time, time)
        attn = td_dot(weights, v)
        attn = tf.transpose(attn, (0, 2, 1, 3))  # (bs, time, num_heads, head_size)
        out = tf.reshape(attn, (-1, inputs.shape[1], self.num_heads * self.head_size))
        return self.out_proj(out)


class Upsample(keras.layers.Layer):
    def __init__(self, channels, **kwargs):
        super().__init__(**kwargs)
        self.ups = keras.layers.UpSampling2D(2)
        self.conv = PaddedConv2D(channels, 3, padding=1)

    def call(self, inputs):
        x = self.ups(inputs)
        return self.conv(x)


class GEGLU(keras.layers.Layer):
    def __init__(self, output_dim, **kwargs):
        super().__init__(**kwargs)
        self.output_dim = output_dim
        self.dense = keras.layers.Dense(output_dim * 2)
        self.dense.trainable = False

    def call(self, inputs):
        x = self.dense(inputs)
        x, gate = x[..., : self.output_dim], x[..., self.output_dim :]
        tanh_res = keras.activations.tanh(
            gate * 0.7978845608 * (1 + 0.044715 * (gate**2))
        )
        return x * 0.5 * gate * (1 + tanh_res)


def td_dot(a, b):
    aa = tf.reshape(a, (-1, a.shape[2], a.shape[3]))
    bb = tf.reshape(b, (-1, b.shape[2], b.shape[3]))
    cc = keras.backend.batch_dot(aa, bb)
    return tf.reshape(cc, (-1, a.shape[1], cc.shape[1], cc.shape[2]))
