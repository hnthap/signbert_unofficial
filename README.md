# SignBERT+ Unofficial Windows Implementation

This repository contains the unofficial implementation of [SignBERT+: Hand-model-aware Self-supervised Pre-training for Sign Language Understanding](https://ieeexplore.ieee.org/abstract/document/10109128).

I use Windows personally, and the setup process listed below is for Windows only. I may make this cross-platform if necessary.

## After cloning

The contents of submodules are not cloned by default. Once cloned, execute the
following:

```powershell
git submodule init
git submodule update
```

Or clone using the flag:

```powershell
git clone --recurse-submodules <REPO_URL>
```

## Download MANO files

1. Go to the [MANO website](http://mano.is.tue.mpg.de/)
2. Create an account
3. Download Models & Code
4. Extract the `*.zip` inside the `signbert/model/thirdparty/mano_assets` folder
5. Folder structure should look like this:

```powershell
mano_assets/
    ├── info.txt
    ├── __init__.py
    ├── LICENSE.txt
    ├── models
    │   ├── info.txt
    │   ├── LICENSE.txt
    │   ├── MANO_LEFT.pkl
    │   ├── MANO_RIGHT.pkl
    │   ├── SMPLH_female.pkl
    │   └── SMPLH_male.pkl
    └── webuser
        └── ...
```

## Create virtual environment

```powershell
conda create --name signbertpcu121 python=3.9.18
conda activate signbertpcu121
```

## Install dependencies

```powershell
# PyTorch

pip install torch==2.4.1 torchvision==0.19.1 torchaudio==2.4.1 --index-url https://download.pytorch.org/whl/cu121

# manotorch

cd signbert/model/thirdparty/manotorch
pip install .
cd ../../../..

# Build PyTorch3D from source
# Requires MSVC v14 or higher
# https://github.com/facebookresearch/pytorch3d

pip install "git+https://github.com/facebookresearch/pytorch3d.git@v0.7.7"

# Other packages

conda env update --file cu121.environment.yml
```

## Run a training session

⚠️ I did not actually try this.

```powershell
python train.py --config configs/pretrain.yml
```

## Run finetuning

⚠️ I did not actually try this.

```powershell
python finetune.py --config finetune/configs/ISLR_MSASL.yml
--ckpt checkpoints/pretrain/ckpts/<CKPT_NAME>.ckpt
```

## Visualize logs with Tensorboard

⚠️ I did not actually try this.

```powershell
tensorboard --logdir <LOGS_DPATH>
```

## Create visualization

⚠️ I did not actually try this.

```powershell
cd visualization
python create_visualization.py
```

If you find this code useful for your research, please consider citing:

```txt
@article{hu2023signbert+,
    title={SignBERT+: Hand-model-aware Self-supervised Pre-training for Sign Language Understanding},
    author={Hu, Hezhen and Zhao, Weichao and Zhou, Wengang and Li, Houqiang},
    journal={IEEE Transactions on Pattern Analysis and Machine Intelligence},
    year={2023},
    publisher={IEEE}
}
```
