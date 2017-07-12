# Original Version: Taehoon Kim (http://carpedm20.github.io)
#   + Source: https://github.com/carpedm20/DCGAN-tensorflow/blob/e30539fb5e20d5a0fed40935853da97e9e55eee8/model.py
#   + License: MIT
# [2016-08-05] Modifications for Completion: Brandon Amos (http://bamos.github.io)
#   + License: MIT
# [2017-07] Modifications for sText2Image: Shangzhe Wu
#   + License: MIT

from __future__ import division
import os
import time
from glob import glob
import tensorflow as tf
from six.moves import xrange

from ops import *
from utils import *

import pickle

import pdb

class DCGAN(object):
    # sample_size = 64
    def __init__(self, sess, image_size=64, is_crop=False,
                 batch_size=64, sample_size=64, text_vector_dim=100,
                 z_dim=100, t_dim=256, gf_dim=64, df_dim=64,
                 gfc_dim=1024, dfc_dim=1024, c_dim=3,
                 checkpoint_dir=None, sample_dir=None, lam=0.1):
        """

        Args:
            sess: TensorFlow session
            batch_size: The size of batch. Should be specified before training.
            z_dim: (optional) Dimension of dim for Z. [100]
            t_dim: (optional) Dimension of text features. [256]
            gf_dim: (optional) Dimension of gen filters in first conv layer. [64]
            df_dim: (optional) Dimension of discrim filters in first conv layer. [64]
            gfc_dim: (optional) Dimension of gen untis for for fully connected layer. [1024]
            dfc_dim: (optional) Dimension of discrim units for fully connected layer. [1024]
            c_dim: (optional) Dimension of image color. [3]
        """
        self.sess = sess
        self.is_crop = is_crop
        self.batch_size = batch_size
        self.text_vector_dim = text_vector_dim
        self.image_size = image_size
        self.sample_size = sample_size
        self.image_shape = [image_size, image_size * 2, 3]
        # self.image_shape = [image_size, image_size, 3]

        self.z_dim = z_dim
        self.t_dim = t_dim

        self.gf_dim = gf_dim
        self.df_dim = df_dim

        self.gfc_dim = gfc_dim
        self.dfc_dim = dfc_dim

        self.lam = lam

        self.c_dim = 3

        # batch normalization : deals with poor initialization helps gradient flow
        self.d_bn1 = batch_norm(name='d_bn1')
        self.d_bn2 = batch_norm(name='d_bn2')
        self.d_bn3 = batch_norm(name='d_bn3')
        self.d_bn4 = batch_norm(name='d_bn4')

        self.g_bn0 = batch_norm(name='g_bn0')
        self.g_bn1 = batch_norm(name='g_bn1')
        self.g_bn2 = batch_norm(name='g_bn2')
        self.g_bn3 = batch_norm(name='g_bn3')

        self.checkpoint_dir = checkpoint_dir
        self.sample_dir = sample_dir
        self.build_model()

        self.model_name = "DCGAN.model"

    def build_model(self):
        self.images = tf.placeholder(
            tf.float32, [self.batch_size] + self.image_shape, name='real_images')
        self.sample_images= tf.placeholder(
            tf.float32, [self.batch_size] + self.image_shape, name='sample_images')

        self.z = tf.placeholder(tf.float32, [self.batch_size, self.z_dim], name='z')
        self.z_sum = tf.summary.histogram("z", self.z)

        ########## Elliott ##########
        self.t = tf.placeholder(tf.float32, [self.batch_size, self.text_vector_dim], name='t')
        self.t_sum = tf.summary.histogram("t", self.t)

        self.images_wr = tf.placeholder(
            tf.float32, [self.batch_size] + self.image_shape, name='wrong_images')

        self.G = self.generator(self.z, self.t)
        self.D, self.D_logits = self.discriminator(self.images, self.t)
        self.D_, self.D_logits_ = self.discriminator(self.G, self.t, reuse=True)
        self.D_wr, self.D_logits_wr = self.discriminator(self.images_wr, self.t, reuse=True)

        self.sampler = self.sampler(self.z, self.t)

        self.d_sum = tf.summary.histogram("d", self.D)
        self.d__sum = tf.summary.histogram("d_", self.D_)
        self.d_wr_sum = tf.summary.histogram("d_wr", self.D_wr)
        self.G_sum = tf.image_summary("G", self.G)

        #self.d_loss_real = tf.reduce_mean(
        #    tf.nn.sigmoid_cross_entropy_with_logits(self.D_logits,
        #                                            tf.ones_like(self.D)))
        #self.d_loss_fake = tf.reduce_mean(
        #    tf.nn.sigmoid_cross_entropy_with_logits(self.D_logits_,
        #                                            tf.zeros_like(self.D_)))
        #self.d_loss_wrong = tf.reduce_mean(
        #    tf.nn.sigmoid_cross_entropy_with_logits(self.D_logits_wr,
        #                                            tf.zeros_like(self.D_wr)))
        #self.g_loss = tf.reduce_mean(
        #    tf.nn.sigmoid_cross_entropy_with_logits(self.D_logits_,
        #                                            tf.ones_like(self.D_)))

        self.d_loss_real = 0.5 * tf.reduce_mean((self.D_logits - tf.ones_like(self.D))**2)
        self.d_loss_fake = 0.5 * tf.reduce_mean((self.D_logits_ + tf.ones_like(self.D_))**2)
        self.d_loss_wrong = 0.5 * tf.reduce_mean((self.D_logits_wr + tf.ones_like(self.D_wr))**2)
        self.g_loss = 0.5 * tf.reduce_mean((self.D_logits_ - tf.zeros_like(self.D_))**2) 

        self.d_loss_real_sum = tf.scalar_summary("d_loss_real", self.d_loss_real)
        self.d_loss_fake_sum = tf.scalar_summary("d_loss_fake", self.d_loss_fake)
        self.d_loss_wrong_sum = tf.scalar_summary("d_loss_wrong", self.d_loss_wrong)

        self.d_loss = self.d_loss_real + self.d_loss_fake + self.d_loss_wrong

        self.g_loss_sum = tf.scalar_summary("g_loss", self.g_loss)
        self.d_loss_sum = tf.scalar_summary("d_loss", self.d_loss)

        t_vars = tf.trainable_variables()

        self.d_vars = [var for var in t_vars if 'd_' in var.name]
        self.g_vars = [var for var in t_vars if 'g_' in var.name]

        self.saver = tf.train.Saver(max_to_keep=10)

        # Completion.
        self.mask = tf.placeholder(tf.float32, [None] + self.image_shape, name='mask')
        self.contextual_loss = tf.reduce_sum(
            tf.contrib.layers.flatten(
                tf.abs(tf.mul(self.mask, self.G) - tf.mul(self.mask, self.images))), 1)
        self.perceptual_loss = self.g_loss
        self.complete_loss = self.contextual_loss + self.lam*self.perceptual_loss
        self.grad_complete_loss = tf.gradients(self.complete_loss, self.z)

    def train(self, config):
        #pdb.set_trace()

        data = glob(os.path.join(config.dataset, "*.png"))
        #np.random.shuffle(data)
        print (os.path.join(config.dataset, "*.png"))
        assert(len(data) > 0)
        
        ########## Elliott ##########
        text_data = pickle.load(open(config.text_path, 'rb'))


        d_optim = tf.train.AdamOptimizer(config.learning_rate, beta1=config.beta1) \
                          .minimize(self.d_loss, var_list=self.d_vars)
        g_optim = tf.train.AdamOptimizer(config.learning_rate, beta1=config.beta1) \
                          .minimize(self.g_loss, var_list=self.g_vars)
        tf.initialize_all_variables().run()

        self.g_sum = tf.merge_summary(
            [self.z_sum, self.t_sum, self.d__sum, self.G_sum, self.d_loss_fake_sum, self.g_loss_sum])
        self.d_sum = tf.merge_summary(
            [self.z_sum, self.t_sum, self.d_sum, self.d_wr_sum, self.d_loss_real_sum, self.d_loss_wrong_sum, self.d_loss_sum])
        self.writer = tf.train.SummaryWriter("./logs", self.sess.graph)

        sample_z = np.random.uniform(-1, 1, size=(self.sample_size , self.z_dim))
        sample_files = data[0:self.sample_size]
        sample = [get_image(sample_file, self.image_size, is_crop=self.is_crop) for sample_file in sample_files]
        sample_images = np.array(sample).astype(np.float32)

        sample_t_ = [get_text_batch(os.path.basename(sample_file), text_data) for sample_file in sample_files]
        sample_t = np.array(sample_t_).astype(np.float32)

        # for face labels
        with open(os.path.join(self.sample_dir, 'sampled_texts.txt'), 'wb') as f:
            #label_headers = torchfile.load('./datasets/celeba/labelHeader.dmp')
            #f.write(b'\t'.join(label_headers) + b'\r\n')
            np.savetxt(f, sample_t, fmt='%i', delimiter='\t')

        counter = 1
        start_time = time.time()

        if self.load(self.checkpoint_dir):
            print("""

======
An existing model was found in the checkpoint directory.
If you just cloned this repository, it's Brandon Amos'
trained model for faces that's used in the post.
If you want to train a new model from scratch,
delete the checkpoint directory or specify a different
--checkpoint_dir argument.
======

""")
        else:
            print("""

======
An existing model was not found in the checkpoint directory.
Initializing a new one.
======

""")        

        for epoch in xrange(config.epoch):
            data = glob(os.path.join(config.dataset, "*.png"))
            batch_idxs = min(len(data), config.train_size) // self.batch_size

            for idx in xrange(0, batch_idxs):
                data_start_time = time.time()
                batch_files = data[idx*config.batch_size:(idx+1)*config.batch_size]
                batch = [get_image(batch_file, self.image_size, is_crop=self.is_crop)
                         for batch_file in batch_files]
                batch_images = np.array(batch).astype(np.float32)

                batch_z = np.random.uniform(-1, 1, [config.batch_size, self.z_dim]) \
                            .astype(np.float32)

                ########## Elliott ##########
                batch_t_ = [get_text_batch(os.path.basename(batch_file), text_data)
                         for batch_file in batch_files]
                batch_t = np.array(batch_t_).astype(np.float32)
                idx_wr = np.random.randint(batch_idxs)
                while (idx_wr == idx):
                    idx_wr = np.random.randint(batch_idxs)

                batch_files_wr = data[idx_wr*config.batch_size:(idx_wr+1)*config.batch_size]
                batch_wr = [get_image(batch_file_wr, self.image_size, is_crop=self.is_crop)
                         for batch_file_wr in batch_files_wr]

                data_time = time.time() - data_start_time

                # Update D network
                _, summary_str = self.sess.run([d_optim, self.d_sum],
                    feed_dict={ self.images: batch_images, self.images_wr: batch_wr, self.z: batch_z, self.t: batch_t })
                self.writer.add_summary(summary_str, counter)

                # Update G network
                _, summary_str = self.sess.run([g_optim, self.g_sum],
                    feed_dict={ self.z: batch_z, self.t: batch_t })
                self.writer.add_summary(summary_str, counter)

                # Run g_optim twice to make sure that d_loss does not go to zero (different from paper)
                _, summary_str = self.sess.run([g_optim, self.g_sum],
                    feed_dict={ self.z: batch_z, self.t: batch_t })
                self.writer.add_summary(summary_str, counter)

                errD_fake = self.d_loss_fake.eval({self.z: batch_z, self.t: batch_t})
                errD_real = self.d_loss_real.eval({self.images: batch_images, self.t: batch_t})
                errG = self.g_loss.eval({self.z: batch_z, self.t: batch_t})

                counter += 1
                print("Epoch: [%2d] [%4d/%4d] data_time: %4.4f, time: %4.4f, d_loss: %.8f, g_loss: %.8f" \
                    % (epoch, idx, batch_idxs, data_time,
                        time.time() - start_time, errD_fake+errD_real, errG))
                
                # if np.mod(counter, 100) == 1: 
                if np.mod(counter, 100) == 1:
                    samples = self.sess.run(
                        [self.sampler], feed_dict={self.z: sample_z, self.t: sample_t}
                    )
                    # [8, 8]
                    save_images(samples[0], [8, 8],
                                os.path.join(self.sample_dir, 'train_{:02d}_{:04d}.png'.format(epoch, idx)))
                    #print("[Sample] d_loss: %.8f, g_loss: %.8f" % (d_loss, g_loss))

                if np.mod(counter, 500) == 2:
                    self.save(config.checkpoint_dir, counter)


    def complete(self, config):
        os.makedirs(os.path.join(config.outDir, 'hats_imgs'))
        os.makedirs(os.path.join(config.outDir, 'completed'))

        tf.initialize_all_variables().run()

        isLoaded = self.load(self.checkpoint_dir)
        assert(isLoaded)

        # data = glob(os.path.join(config.dataset, "*.png"))
        nImgs = len(config.imgs)

        batch_idxs = int(np.ceil(nImgs/self.batch_size))
        if config.maskType == 'random':
            fraction_masked = 0.8
            mask = np.ones(self.image_shape)
            mask[np.random.random(self.image_shape[:2]) < fraction_masked] = 0.0
        elif config.maskType == 'center':
            scale = 0.25
            assert(scale <= 0.5)
            mask = np.ones(self.image_shape)
            sz = self.image_size
            l = int(self.image_size*scale)
            u = int(self.image_size*(1.0-scale))
            mask[l:u, l:u, :] = 0.0
        elif config.maskType == 'left':
            mask = np.ones(self.image_shape)
            c = self.image_size // 1.4 #2
            mask[:,:c,:] = 0.0
        elif config.maskType == 'right':
            mask = np.ones(self.image_shape)
            mask[:,self.image_size:,:] = 0.0
        elif config.maskType == 'full':
            mask = np.ones(self.image_shape)
        else:
            assert(False)

        # for idx in xrange(0, batch_idxs):
        for idx in xrange(1, 2):
            l = idx*self.batch_size
            u = min((idx+1)*self.batch_size, nImgs)
            batchSz = u-l
            batch_files = config.imgs[l:u]
            batch = [get_image(batch_file, self.image_size, is_crop=self.is_crop)
                     for batch_file in batch_files]
            batch_images = np.array(batch).astype(np.float32)
            if batchSz < self.batch_size:
                print(batchSz)
                padSz = ((0, int(self.batch_size-batchSz)), (0,0), (0,0), (0,0))
                batch_images = np.pad(batch_images, padSz, 'constant')
                batch_images = batch_images.astype(np.float32)

            batch_mask = np.resize(mask, [self.batch_size] + self.image_shape)
            zhats = np.random.uniform(-1, 1, size=(self.batch_size, self.z_dim))
            v = 0

            nRows = np.ceil(batchSz/8)
            nCols = 8
            save_images(batch_images[:batchSz,:,:,:], [nRows,nCols],
                        os.path.join(config.outDir, 'before.png'))
            masked_images = np.multiply(batch_images, batch_mask)
            save_images(masked_images[:batchSz,:,:,:], [nRows,nCols],
                        os.path.join(config.outDir, 'masked.png'))

            for i in xrange(config.nIter):
                fd = {
                    self.z: zhats,
                    self.mask: batch_mask,
                    self.images: batch_images,
                }
                run = [self.complete_loss, self.grad_complete_loss, self.G]
                loss, g, G_imgs = self.sess.run(run, feed_dict=fd)

                v_prev = np.copy(v)
                v = config.momentum*v - config.lr*g[0]
                zhats += -config.momentum * v_prev + (1+config.momentum)*v
                zhats = np.clip(zhats, -1, 1)

                if i % 2 == 0:
                    print(i, np.mean(loss[0:batchSz]))
                    imgName = os.path.join(config.outDir,
                                           'hats_imgs/{:04d}.png'.format(i))
                    nRows = np.ceil(batchSz/8)
                    nCols = 8
                    save_images(G_imgs[:batchSz,:,:,:], [nRows,nCols], imgName)

                    inv_masked_hat_images = np.multiply(G_imgs, 1.0-batch_mask)
                    completeed = masked_images + inv_masked_hat_images
                    imgName = os.path.join(config.outDir,
                                           'completed/{:04d}.png'.format(i))
                    save_images(completeed[:batchSz,:,:,:], [nRows,nCols], imgName)

    def discriminator(self, image, t, reuse=False):
        if reuse:
            tf.get_variable_scope().reuse_variables()

        h0 = lrelu(conv2d(image, self.df_dim, name='d_h0_conv'))
        h1 = lrelu(self.d_bn1(conv2d(h0, self.df_dim*2, name='d_h1_conv')))
        h2 = lrelu(self.d_bn2(conv2d(h1, self.df_dim*4, name='d_h2_conv')))
        h3_ = lrelu(self.d_bn3(conv2d(h2, self.df_dim*8, name='d_h3_conv')))

        ########## Elliott ##########

        t__, h0_t_w, h0_t_b = linear(t, self.t_dim, 'd_h0_t_lin', with_w=True)
        t_ = tf.nn.relu(t__)
        t_ = tf.expand_dims(t_, 1)
        t_ = tf.expand_dims(t_, 2)
        t_tiled = tf.tile(t_, [1,4,8,1], name='tiled_t')


        # pdb.set_trace()


        h3_concat = tf.concat(3, [h3_, t_tiled], name='h3_concat')
        h3 = lrelu(self.d_bn4(conv2d(h3_concat, self.df_dim*8, 1,1,1,1, name = 'd_h3_conv_new')))

        # h4 = linear(tf.reshape(h3, [-1, 8192]), 1, 'd_h3_lin')
        h4 = linear(tf.reshape(h3, [-1, 8192*2]), 1, 'd_h3_lin')

        return tf.nn.sigmoid(h4), h4

    #def generator(self, z):
    #    self.z_, self.h0_w, self.h0_b = linear(z, self.gf_dim*8*4*4, 'g_h0_lin', with_w=True)

    #    self.h0 = tf.reshape(self.z_, [-1, 4, 4, self.gf_dim * 8])
    #    h0 = tf.nn.relu(self.g_bn0(self.h0))

    #    self.h1, self.h1_w, self.h1_b = conv2d_transpose(h0,
    #        [self.batch_size, 8, 8, self.gf_dim*4], name='g_h1', with_w=True)
    #    h1 = tf.nn.relu(self.g_bn1(self.h1))

    #    h2, self.h2_w, self.h2_b = conv2d_transpose(h1,
    #        [self.batch_size, 16, 16, self.gf_dim*2], name='g_h2', with_w=True)
    #    h2 = tf.nn.relu(self.g_bn2(h2))

    #    h3, self.h3_w, self.h3_b = conv2d_transpose(h2,
    #        [self.batch_size, 32, 32, self.gf_dim*1], name='g_h3', with_w=True)
    #    h3 = tf.nn.relu(self.g_bn3(h3))

    #    h4, self.h4_w, self.h4_b = conv2d_transpose(h3,
    #        [self.batch_size, 64, 64, 3], name='g_h4', with_w=True)

    #    return tf.nn.tanh(h4)

    def generator(self, z, t):

        self.t_, self.h0_t_w, self.h0_t_b = linear(t, self.t_dim, 'g_h0_t_lin', with_w=True)
        t_ = tf.nn.relu(self.t_)

        z_concat = tf.concat(1, [z, t_])

        self.z_, self.h0_w, self.h0_b = linear(z_concat, self.gf_dim*8*4*8, 'g_h0_lin', with_w=True)

        self.h0 = tf.reshape(self.z_, [-1, 4, 8, self.gf_dim * 8])
        h0 = tf.nn.relu(self.g_bn0(self.h0))

        self.h1, self.h1_w, self.h1_b = conv2d_transpose(h0,
            [self.batch_size, 8, 16, self.gf_dim*4], name='g_h1', with_w=True)
        h1 = tf.nn.relu(self.g_bn1(self.h1))

        h2, self.h2_w, self.h2_b = conv2d_transpose(h1,
            [self.batch_size, 16, 32, self.gf_dim*2], name='g_h2', with_w=True)
        h2 = tf.nn.relu(self.g_bn2(h2))

        h3, self.h3_w, self.h3_b = conv2d_transpose(h2,
            [self.batch_size, 32, 64, self.gf_dim*1], name='g_h3', with_w=True)
        h3 = tf.nn.relu(self.g_bn3(h3))

        h4, self.h4_w, self.h4_b = conv2d_transpose(h3,
            [self.batch_size, 64, 128, 3], name='g_h4', with_w=True)

        return tf.nn.tanh(h4)


    #def sampler(self, z, y=None):
    #    tf.get_variable_scope().reuse_variables()

    #    h0 = tf.reshape(linear(z, self.gf_dim*8*4*4, 'g_h0_lin'),
    #                    [-1, 4, 4, self.gf_dim * 8])
    #    h0 = tf.nn.relu(self.g_bn0(h0, train=False))

    #    h1 = conv2d_transpose(h0, [self.batch_size, 8, 8, self.gf_dim*4], name='g_h1')
    #    h1 = tf.nn.relu(self.g_bn1(h1, train=False))

    #    h2 = conv2d_transpose(h1, [self.batch_size, 16, 16, self.gf_dim*2], name='g_h2')
    #    h2 = tf.nn.relu(self.g_bn2(h2, train=False))

    #    h3 = conv2d_transpose(h2, [self.batch_size, 32, 32, self.gf_dim*1], name='g_h3')
    #    h3 = tf.nn.relu(self.g_bn3(h3, train=False))

    #    h4 = conv2d_transpose(h3, [self.batch_size, 64, 64, 3], name='g_h4')

    #    return tf.nn.tanh(h4)

    def sampler(self, z, t, y=None):
        tf.get_variable_scope().reuse_variables()

        # t__, h0_t_w, h0_t_b = linear(t, self.t_dim, 'g_h0_t_lin')
        t_ = tf.nn.relu(linear(t, self.t_dim, 'g_h0_t_lin'))

        z_concat = tf.concat(1, [z, t_])

        h0 = tf.reshape(linear(z_concat, self.gf_dim*8*4*8, 'g_h0_lin'),
                        [-1, 4, 8, self.gf_dim * 8])
        h0 = tf.nn.relu(self.g_bn0(h0, train=False))

        h1 = conv2d_transpose(h0, [self.batch_size, 8, 16, self.gf_dim*4], name='g_h1')
        h1 = tf.nn.relu(self.g_bn1(h1, train=False))

        h2 = conv2d_transpose(h1, [self.batch_size, 16, 32, self.gf_dim*2], name='g_h2')
        h2 = tf.nn.relu(self.g_bn2(h2, train=False))

        h3 = conv2d_transpose(h2, [self.batch_size, 32, 64, self.gf_dim*1], name='g_h3')
        h3 = tf.nn.relu(self.g_bn3(h3, train=False))

        h4 = conv2d_transpose(h3, [self.batch_size, 64, 128, 3], name='g_h4')

        return tf.nn.tanh(h4)


    def save(self, checkpoint_dir, step):
        if not os.path.exists(checkpoint_dir):
            os.makedirs(checkpoint_dir)

        self.saver.save(self.sess,
                        os.path.join(checkpoint_dir, self.model_name),
                        global_step=step)

    def load(self, checkpoint_dir):
        print(" [*] Reading checkpoints...")

        ckpt = tf.train.get_checkpoint_state(checkpoint_dir)
        if ckpt and ckpt.model_checkpoint_path:
            self.saver.restore(self.sess, ckpt.model_checkpoint_path)
            return True
        else:
            return False