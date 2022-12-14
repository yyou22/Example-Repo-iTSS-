from __future__ import print_function
import os
import argparse
import torch
import torch.nn as nn
import torch.nn.functional as F
import torchvision
import torch.optim as optim
from torchvision import datasets, transforms
from torchvision.models import resnet101, ResNet101_Weights

parser = argparse.ArgumentParser(description='PyTorch GTSRB TRADES Adversarial Training')
parser.add_argument('--batch-size', type=int, default=64, metavar='N',
					help='input batch size for training (default: 128)')
parser.add_argument('--test-batch-size', type=int, default=64, metavar='N',
					help='input batch size for testing (default: 128)')
parser.add_argument('--epochs', type=int, default=20, metavar='N',
					help='number of epochs to train')
parser.add_argument('--weight-decay', '--wd', default=2e-4,
					type=float, metavar='W')
parser.add_argument('--lr', type=float, default=0.01, metavar='LR',
					help='learning rate')
parser.add_argument('--momentum', type=float, default=0.9, metavar='M',
					help='SGD momentum')
parser.add_argument('--no-cuda', action='store_true', default=False,
					help='disables CUDA training')
parser.add_argument('--epsilon', default=0.031,
					help='perturbation')
parser.add_argument('--num-steps', default=10,
					help='perturb number of steps')
parser.add_argument('--log-interval', type=int, default=50, metavar='N',
					help='how many batches to wait before logging training status')
parser.add_argument('--model-dir', default='./model-gtsrb-ResNet',
					help='directory of model for saving checkpoint')
parser.add_argument('--save-freq', '-s', default=1, type=int, metavar='N',
					help='save frequency')

args = parser.parse_args()

# settings
model_dir = args.model_dir
if not os.path.exists(model_dir):
	os.makedirs(model_dir)
use_cuda = not args.no_cuda and torch.cuda.is_available()
device = torch.device("cuda" if use_cuda else "cpu")
kwargs = {'num_workers': 1, 'pin_memory': True} if use_cuda else {}

# setup data loader
transform_train = transforms.Compose([
    transforms.Resize((96, 96)),
    transforms.RandomRotation(15),
    transforms.ToTensor(),
])
transform_test = transforms.Compose([
    transforms.Resize((96, 96)),
    transforms.ToTensor(),
])

trainset = torchvision.datasets.GTSRB(root="/content/dataset/train", split="train", download=True, transform=transform_train)
testset = torchvision.datasets.GTSRB(root="/content/dataset/test", split="test", download=True, transform=transform_test)

train_loader = torch.utils.data.DataLoader(trainset, batch_size=args.batch_size, shuffle=True, **kwargs)
test_loader = torch.utils.data.DataLoader(testset, batch_size=args.test_batch_size, shuffle=False, **kwargs)

def train(args, model, device, train_loader, optimizer, epoch):

	model.train()
	for batch_idx, (data, target) in enumerate(train_loader):
		data, target = data.to(device), target.to(device)
		optimizer.zero_grad()

		# calculate loss
		loss = F.cross_entropy(model(data), target)

		loss.backward()
		optimizer.step()

		# print progress
		if batch_idx % args.log_interval == 0:
			print('Train Epoch: {} [{}/{} ({:.0f}%)]\tLoss: {:.6f}'.format(
				epoch, batch_idx * len(data), len(train_loader.dataset),
					   100. * batch_idx / len(train_loader), loss.item()))

def eval_train(model, device, train_loader):
	model.eval()
	train_loss = 0
	correct = 0
	with torch.no_grad():
		for data, target in train_loader:
			data, target = data.to(device), target.to(device)
			output = model(data)
			train_loss += F.cross_entropy(output, target, size_average=False).item()
			pred = output.max(1, keepdim=True)[1]
			correct += pred.eq(target.view_as(pred)).sum().item()
	train_loss /= len(train_loader.dataset)
	print('Training: Average loss: {:.4f}, Accuracy: {}/{} ({:.0f}%)'.format(
		train_loss, correct, len(train_loader.dataset),
		100. * correct / len(train_loader.dataset)))
	training_accuracy = correct / len(train_loader.dataset)
	return train_loss, training_accuracy


def eval_test(model, device, test_loader):
	model.eval()
	test_loss = 0
	correct = 0
	with torch.no_grad():
		for data, target in test_loader:
			data, target = data.to(device), target.to(device)
			output = model(data)
			test_loss += F.cross_entropy(output, target, size_average=False).item()
			pred = output.max(1, keepdim=True)[1]
			correct += pred.eq(target.view_as(pred)).sum().item()
	test_loss /= len(test_loader.dataset)
	print('Test: Average loss: {:.4f}, Accuracy: {}/{} ({:.0f}%)'.format(
		test_loss, correct, len(test_loader.dataset),
		100. * correct / len(test_loader.dataset)))
	test_accuracy = correct / len(test_loader.dataset)
	return test_loss, test_accuracy

def adjust_learning_rate(optimizer, epoch):
	"""decrease the learning rate"""
	lr = args.lr
	if epoch >= 5:
		lr = args.lr * 0.1
	if epoch >= 10:
		lr = args.lr * 0.01
	if epoch >= 15:
		lr = args.lr * 0.001
	for param_group in optimizer.param_groups:
		param_group['lr'] = lr

def main():
	model = resnet101(weights=ResNet101_Weights.DEFAULT)
	model.fc = nn.Linear(2048, 43)
	model = model.to(device)

	optimizer = optim.SGD(model.parameters(), lr=args.lr, momentum=args.momentum, weight_decay=args.weight_decay)

	for epoch in range(1, args.epochs + 1):
		# adjust learning rate for SGD
		adjust_learning_rate(optimizer, epoch)

		# adversarial training
		train(args, model, device, train_loader, optimizer, epoch)

		# evaluation on natural examples
		print('================================================================')
		train_loss, train_accuracy = eval_train(model, device, train_loader)
		test_loss, test_accuracy = eval_test(model, device, test_loader)
		print('================================================================')

		# save checkpoint
		if epoch % args.save_freq == 0:
			torch.save(model.state_dict(),
					   os.path.join(model_dir, 'model-res-epoch{}.pt'.format(epoch)))
			torch.save(optimizer.state_dict(),
					   os.path.join(model_dir, 'opt-res-checkpoint_epoch{}.tar'.format(epoch)))

if __name__ == '__main__':
	main()