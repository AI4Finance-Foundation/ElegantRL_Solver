import pickle as pkl
import torch as th
import time
import os
from net import Net_MIMO
from tqdm import tqdm

num_users = 4
num_antennas = 4
total_power = 10 
noise_power = 1
num_training_epochs = 40000 
fullspace_dim = 2 * num_users * num_antennas
num_update_each_subspace = 400
num_epoch_test = 1000
cur_subspace_num = 1
curriculum_base_vectors, _ = th.linalg.qr(th.rand(fullspace_dim, fullspace_dim, dtype=th.float))
total_steps = 0
learning_rate = 5e-5
batch_size = 8192
mid_dim = 512
num_loop = 5
subspace = 1
total_steps = 1
file_name = f"lr_{learning_rate}_bs_{batch_size}_middim_{mid_dim}"
device = th.device("cuda:0" if th.cuda.is_available() else "cpu")
def compute_channel(num_antennas, num_users, fullspace_dim, batch_size , subspace, base_vectors):
  coordinates = th.randn(batch_size, subspace, 1)
  channel = th.bmm(base_vectors[:subspace].T.repeat(batch_size, 1).reshape(batch_size, base_vectors.shape[1], fullspace_dim), coordinates).reshape(-1 ,2 * num_users * num_antennas) * (( 32 / subspace) ** 0.5) * (num_antennas * num_users) ** 0.5
  channel = (channel / channel.norm(dim=1, keepdim = True)).reshape(-1, 2, num_users, num_antennas)
  return (channel[:, 0] + channel[:, 1] * 1.j).reshape(-1, num_users, num_antennas)
def save(file_name):
  file_list = os.listdir()
  if file_name not in file_list:
    os.mkdir(file_name)
  file_list = os.listdir('./{}/'.format(file_name))
  max_exp_id = 0
  for exp_id in file_list:
    if int(exp_id) + 1 > max_exp_id:
      max_exp_id = int(exp_id) + 1
  os.mkdir('./{}/{}/'.format(file_name, exp_id))
  return f"./{file_name}/{max_exp_id}/"

if __name__  == "__main__":
  mmse_net = Net_MIMO(mid_dim).to(device)
  optimizer = th.optim.Adam(mmse_net.parameters(), lr=learning_rate)
  save_path = save(file_name)
  print("start of session")
  start_of_time = time.time()
  pbar = tqdm(range(num_training_epochs))      
  obj = 0
  try:
    for i in pbar:
      pbar.set_description(f" training_loss: { obj.item():.3f} | gpu memory: {th.cuda.memory_allocated():3d}")
      obj = 0
      if total_steps % num_epoch_test == 0:
        th.save(mmse_net.state_dict(), save_path+f"{total_steps}.pth")
      if total_steps % num_update_each_subspace == 0 and subspace < 32:
        subspace +=1
        channel = compute_channel(num_antennas, num_users, fullspace_dim, batch_size, total_power,total_steps, subspace, curriculum_base_vectors).to(device)
      else:
        channel = th.randn(batch_size, num_antennas, num_users, dtype=th.cfloat).to(device)
      total_steps += 1
      for batch_i in range(int(4096 / batch_size)):
        net_input = th.cat((th.as_tensor(channel.real).reshape(-1, num_users * num_antennas), th.as_tensor(channel.imag).reshape(-1, num_users * num_antennas)), 1).to(device)
        input_w_unflatten = mmse_net.calc_mmse(channel).to(device)
        input_w= th.cat((th.as_tensor(input_w_unflatten.real).reshape(-1, num_users * num_antennas), th.as_tensor(input_w_unflatten.imag).reshape(-1, num_users * num_antennas)), 1).to(device)
        for _ in range(num_loop):
          input_hw_unflatten = th.bmm(channel, input_w_unflatten.transpose(1,2).conj())
          input_hw = th.cat((th.as_tensor(input_hw_unflatten.real).reshape(-1, num_users * num_antennas), th.as_tensor(input_hw_unflatten.imag).reshape(-1, num_users * num_antennas)), 1).to(device)
          net_output = mmse_net(th.cat((net_input, input_w, input_hw), 1), input_hw_unflatten, channel)
          output_w = (net_output.reshape(batch_size, 2, num_users * num_antennas)[:, 0] + net_output.reshape(batch_size, 2, num_users * num_antennas)[:, 1] * 1j).reshape(-1, num_users, num_antennas)
          obj -= mmse_net.calc_wsr(channel, output_w, noise_power).sum()
      optimizer.zero_grad()
      obj.backward()
      optimizer.step()
  except KeyboardInterrupt:
    th.save(mmse_net.state_dict(), save_path+f"{total_steps}.pth")
    exit()
  th.save(mmse_net.state_dict(), save_path+f"{total_steps}.pth")
  print("Training took:", time.time()-start_of_time)