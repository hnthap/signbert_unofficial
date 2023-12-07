import torch
import numpy as np
import lightning.pytorch as pl

from signbert.utils import my_import
from signbert.metrics.PCK import PCK, PCKAUC
from signbert.model.hand_model.HandAwareModelDecoder import HandAwareModelDecoder
# from signbert.model.hand_decoder import HandAwareModelDecoder
from IPython import embed; from sys import exit


class SignBertModel(pl.LightningModule):

    def __init__(
            self, 
            in_channels, 
            num_hid, 
            num_heads,
            tformer_n_layers,
            tformer_dropout,
            eps, 
            lmbd, 
            weight_beta, 
            weight_delta,
            lr,
            hand_cluster,
            n_pca_components,
            gesture_extractor_cls,
            gesture_extractor_args,
            total_steps=None,
            normalize_inputs=False,
            use_pca=True,
            *args,
            **kwargs,
        ):
        super().__init__()
        self.save_hyperparameters()

        self.in_channels = in_channels
        self.num_hid = num_hid
        self.num_heads = num_heads
        self.tformer_n_layers = tformer_n_layers
        self.tformer_dropout = tformer_dropout
        self.eps = eps
        self.lmbd = lmbd
        self.weight_beta = weight_beta
        self.weight_delta = weight_delta
        self.total_steps = total_steps
        self.lr = lr
        self.hand_cluster = hand_cluster
        self.n_pca_components = n_pca_components
        self.gesture_extractor_cls = my_import(gesture_extractor_cls)
        self.gesture_extractor_args = gesture_extractor_args
        self.normalize_inputs = normalize_inputs
        self.use_pca = use_pca

        num_hid_mult = 1 if hand_cluster else 21

        # self.ge = GestureExtractor(in_channels=in_channels, num_hid=num_hid)
        # self.ge = GestureExtractorSpatTemp(
        #     in_channels=in_channels,
        #     inter_channels=[num_hid, num_hid],
        #     fc_unit=num_hid,
        #     layout='mediapipe_hand',
        #     strategy='spatial',
        #     pad=1,
        # )
        self.ge = self.gesture_extractor_cls(**gesture_extractor_args)
        # TODO: remove hard coded value
        el = torch.nn.TransformerEncoderLayer(d_model=num_hid*num_hid_mult, nhead=num_heads, batch_first=True, dropout=tformer_dropout)
        self.te = torch.nn.TransformerEncoder(el, num_layers=tformer_n_layers)
        self.hd = HandAwareModelDecoder(
            in_features=num_hid*num_hid_mult,
            n_pca_components=n_pca_components, 
            mano_model_file='/home/gts/projects/jsoutelo/SignBERT+/signbert/model/hand_model/MANO_RIGHT_npy.pkl',
            use_pca=use_pca
        )
        # self.hd = HandAwareModelDecoder(
        #     in_features=num_hid*num_hid_mult,
        #     n_pca_components=self.n_pca_components,
        # )
        self.train_pck_20 = PCK(thr=20)
        self.train_pck_auc_20_40 = PCKAUC(thr_min=20, thr_max=40)
        self.val_pck_20 = PCK(thr=20)
        self.val_pck_auc_20_40 = PCKAUC(thr_min=20, thr_max=40)

        self.train_step_losses = []
        self.val_step_losses = []

    def forward(self, x):
        x = self.ge(x)
        # Remove last dimension M and permute to be (N, T, C, V)
        x = x.squeeze(-1).permute(0, 2, 1, 3).contiguous()
        N, T, C, V = x.shape
        x = x.view(N, T, C*V)
        x = self.te(x)
        x, theta, beta, hand_mesh, c_r, c_s, c_o, center_jt, jt_3d = self.hd(x)

        return x, theta, beta, hand_mesh, c_r, c_s, c_o, center_jt, jt_3d

    def training_step(self, batch):
        _, x_or, x_masked, scores, masked_frames_idxs = batch
        (logits, theta, beta, _, _, _, _, _, _) = self(x_masked)

        # Loss only applied on frames with masked joints
        valid_idxs = torch.where(masked_frames_idxs != -1.)
        logits = logits[valid_idxs]
        x_or = x_or[valid_idxs]
        scores = scores[valid_idxs]
        # Compute LRec
        lrec = torch.norm(logits[scores>self.eps] - x_or[scores>=self.eps], p=1, dim=1).sum()
        beta_t_minus_one = torch.roll(beta, shifts=1, dims=1)
        beta_t_minus_one[:, 0] = 0.
        lreg = torch.norm(theta, 2) + self.weight_beta * torch.norm(beta, 2) + \
            self.weight_delta * torch.norm(beta - beta_t_minus_one, 2)
        loss = lrec + (self.lmbd * lreg)
        
        self.train_step_losses.append(loss)

        if self.normalize_inputs:
            if not hasattr(self, 'means') or not hasattr(self, 'stds'):
                self.means = np.load(self.trainer.datamodule.MEANS_NPY_FPATH).to(self.device)
                self.stds = np.load(self.trainer.datamodule.STDS_NPY_FPATH).to(self.device)
            logits = (logits * self.stds) + self.means
            x_or = (x_or * self.stds) + self.means

        self.train_pck_20(preds=logits, target=x_or)
        self.train_pck_auc_20_40(preds=logits, target=x_or)

        self.log('train_loss', loss, on_step=True, prog_bar=True)
        self.log('train_PCK_20', self.train_pck_20, on_step=True, on_epoch=False)
        self.log('train_PCK_AUC_20-40', self.train_pck_auc_20_40, on_step=True, on_epoch=False)

        return loss

    def on_train_epoch_end(self):
        mean_epoch_loss = torch.stack(self.train_step_losses).mean()
        self.logger.experiment.add_scalars("losses", {"train_loss": mean_epoch_loss}, global_step=self.current_epoch)
        self.train_step_losses.clear()

    def validation_step(self, batch, batch_idx):
        _, x_or, x_masked, scores, masked_frames_idxs = batch
        (logits, beta, theta, _, _, _, _, _, _) = self(x_masked)

        valid_idxs = torch.where(masked_frames_idxs != -1.)
        logits = logits[valid_idxs]
        x_or = x_or[valid_idxs]
        scores = scores[valid_idxs]
        # Compute LRec
        lrec = torch.norm(logits[scores>self.eps] - x_or[scores>=self.eps], p=1, dim=1).sum()
        beta_t_minus_one = torch.roll(beta, shifts=1, dims=1)
        beta_t_minus_one[:, 0] = 0.
        lreg = torch.norm(theta, 2) + self.weight_beta * torch.norm(beta, 2) + \
            self.weight_delta * torch.norm(beta - beta_t_minus_one, 2)
        loss = lrec + (self.lmbd * lreg)

        self.val_step_losses.append(loss)

        if self.normalize_inputs:
            if not hasattr(self, 'means') or not hasattr(self, 'stds'):
                self.means = torch.tensor(np.load(self.trainer.datamodule.MEANS_NPY_FPATH)).to(self.device)
                self.stds = torch.tensor(np.load(self.trainer.datamodule.STDS_NPY_FPATH)).to(self.device)
            logits = (logits * self.stds) + self.means
            x_or = (x_or * self.stds) + self.means

        self.val_pck_20(preds=logits, target=x_or)
        self.val_pck_auc_20_40(preds=logits, target=x_or)
        
        self.log('val_loss', loss, on_step=False, prog_bar=True)
        self.log('val_PCK_20', self.val_pck_20, on_step=False, on_epoch=True, prog_bar=True)
        self.log('val_PCK_AUC_20_40', self.val_pck_auc_20_40, on_step=False, on_epoch=True)

    def on_validation_epoch_end(self):
        mean_epoch_loss = torch.stack(self.val_step_losses).mean()
        self.logger.experiment.add_scalars("losses", {"val_loss": mean_epoch_loss}, global_step=self.current_epoch)
        self.val_step_losses.clear()
        
    def configure_optimizers(self):
        optimizer = torch.optim.Adam(self.parameters(), lr=self.lr, weight_decay=0.01)
        # lr_scheduler_config = dict(
        #     scheduler=torch.optim.lr_scheduler.OneCycleLR(
        #         optimizer, 
        #         max_lr=1e-4,
        #         total_steps=self.total_steps,
        #         pct_start=0.1,
        #         anneal_strategy='linear'
        #     )
        # )

        return dict(
            optimizer=optimizer,
            # lr_scheduler=lr_scheduler_config
        )


if __name__ == '__main__':
    import numpy as np
    from signbert.data_modules.MaskKeypointDataset import MaskKeypointDataset

    dataset = MaskKeypointDataset(
        npy_fpath='/home/temporal2/jsoutelo/datasets/HANDS17/preprocess/X_train.npy',
        R=0.2,
        m=5,
        K=6
    )
    # TODO
    # get parameters from paper
    model = SignBertModel(in_channels=2, num_hid=256, num_heads=4, tformer_n_layers=2, eps=0.3, weight_beta=0.2, weight_delta=0.2)

    seq, score, masked_frames_idxs = dataset[0]
    seq = torch.tensor(np.stack((seq, seq)).astype(np.float32))
    masked_frames_idxs = torch.tensor(np.stack((masked_frames_idxs,masked_frames_idxs)).astype(np.int32))
    batch = (seq, masked_frames_idxs)

    out = model(batch[0])

    print(f'{out[0].shape=}')
    embed(); exit()

