# Implementation of DreamBooth using KerasCV and TensorFlow

This repository provides an implementation of [DreamBooth](https://arxiv.org/abs/2208.12242) using KerasCV and TensorFlow. The implementation is heavily referred from Hugging Face's `diffusers` [example](https://github.com/huggingface/diffusers/tree/main/examples/dreambooth).

DreamBooth is a way of quickly teaching (fine-tuning) Stable Diffusion about new visual concepts. For more details, refer to [this document](https://dreambooth.github.io/).

## Steps to perform DreamBooth training using the codebase

1. Install the pre-requisites: `pip install -r requirements.txt`.

2. You first need to choose a class to which a unique identifier is appended. This repository codebase was tested using `sks` as the unique idenitifer and `dog` as the class.

    Then two types of prompts are generated: 

    (a) **instance prompt**: f"a photo of {self.unique_id} {self.class_category}"
    (b) **class prompt**: f"a photo of {self.class_category}"

3. **Instance images**
    
    Get a few images (3 - 10) that are representative of the concept the model is going to be fine-tuned with. These images would be associated with the `instance_prompt`. These images are referred to as the `instance_images` from the codebase. Archive these images and host them somewhere online such that the archive can be downloaded using `tf.keras.utils.get_file()` function internally.

4. **Class images**
    
    DreamBooth uses prior-preservation loss to regularize training. Long story cut short,
prior-preservation loss helps the model to slowly adapt to the new concept under consideration from any prior knowledge it may have had about the concept. To use prior-preservation loss, we need the class prompt as shown above. The class prompt is used to generate a pre-defined number of images which are used for computing the final loss used for DreamBooth training. 

    As per [this resource](https://github.com/huggingface/diffusers/tree/main/examples/dreambooth), 200 - 300 images generated using the class prompt work well for most cases. 

    So, after you have decided `instance_prompt` and `class_prompt`, use [this Colab Notebook](https://colab.research.google.com/github/sayakpaul/dreambooth-keras/blob/main/notebooks/generate_class_priors.ipynb) to generate some images that would be used for training with the prior-preservation loss. Then archive the generated images as a single archive and host it online such that it can be downloaded using using `tf.keras.utils.get_file()` function internally. In the codebase, we simply refer to these images as `class_images`.
    
> For people to easily test this codebase, we hosted the instance and class images [here](https://huggingface.co/datasets/sayakpaul/sample-datasets/tree/main). 

5. Launch training! There are a number of hyperparameters you can play around with. Refer to the `train_dreambooth.py` script to know more about them. Here's a command that launches training with mixed-precision and other default values:

```bash=
python train_dreambooth.py --mp
```

You can also fine-tune the text encoder by specifying the `--train_text_encoder` option. 

Additionally, the script supports integration with [Weights and Biases (`wandb`)](https://wandb.ai/). if you specify `--log_wandb`, then it will perform inference with the DreamBoothed model parameters and log the generated images to `wandb` alongside the model parameters as artifacts. [Here's](https://wandb.ai/sayakpaul/dreambooth-keras/runs/este2e4c) an example `wandb` run where you can find the generated images as well as the [model parameters](https://wandb.ai/sayakpaul/dreambooth-keras/artifacts/model/run_este2e4c_model/v0/files). 

## Inference

TBA

## Results

We have tested dreambooth in two different methods: (a) fine-tuning the diffusion model only (b) fine-tuning the diffusion model along with text encoder. The experiments were conducted with vairous range of hyperparameters of `learning rate` and `training steps` for training and of `number of steps` and `unconditional guidance scale`(ugs) for inference, but only the best looking results are included here. If you are curious how different hyperparameters affect the resultant image quality, find the link of the full reports in each section.

### (a) Fine-tuning diffusion model

TBA

### (b) Fine-tuning text encoder + diffusion model

<div align="center">
<table>
  <tr>
    <th>Images</th>
    <th>Steps</th>
    <th>ugs</th>
  </tr>
  <tr>
    <td><img src="https://i.ibb.co/BNVtwDB/dog.png"/></td>
    <td>75</td>
    <td>15</td>
  </tr>
  <tr>
    <td><img src="https://i.ibb.co/zWMzxq2/dog-2.png"/></td>
    <td>75</td>
    <td>30</td>
  </tr>  
</table>
<sub>"A photo of sks dog in a bucket" </sub> 

<sub> w/ learning rate=9e-06, max train steps=200 (<a href="https://huggingface.co/chansung/dreambooth-dog">weights</a> | <a href="https://wandb.ai/chansung18/dreambooth-keras-generating-images?workspace=user-chansung18">reports</a>)</sub>
</div><br>


<div align="center">
<table>
  <tr>
    <th>Images</th>
    <th>Steps</th>
    <th>ugs</th>
  </tr>
  <tr>
    <td><img src="https://i.ibb.co/XYz3s5N/chansung.png"/></td>
    <td>150</td>
    <td>15</td>
  </tr>
  <tr>
    <td><img src="https://i.ibb.co/mFMZG04/chansung-2.png"/></td>
    <td>75</td>
    <td>30</td>
  </tr>  
</table>
<sub>"A photo of sks person without mustache, handsome, ultra realistic, 4k, 8k"</sub> 

<sub> w/ learning rate=9e-06, max train steps=200 (<a href="https://huggingface.co/datasets/chansung/me">datasets</a> | <a href="https://wandb.ai/chansung18/dreambooth-generate-me?workspace=user-chansung18">reports</a>)</sub>
</div><br>


## Acknowledgements

* Thanks to Hugging Face for providing the original example. It's very readable and easy to understand.
* Thanks to the ML Developer Programs' team at Google for providing GCP credits.