const specs = require('../../utils/specs');
const imageUtil = require('../../utils/image');

Page({
  data: {
    photoSrc: null,           // 生成好的照片路径
    bgColorHex: '#ffffff',    // 当前底色
    selectedColorId: 'white', // 当前选择的颜色ID
    selectedSpecId: null,    // 当前规格ID
    specTags: [],            // 规格标签（规格+尺寸）
    colors: [],              // 所有底色
    allSpecs: [],            // 所有规格
    selectedLayout: 'single', // 排版模式
    showPreview: false,      // 是否显示排版预览
    previewSrc: null,        // 排版预览图
    layoutModes: [           // 排版选项
      { id: 'single', label: '单张', icon: '🖼️' },
      { id: '4x2', label: '4×2排', icon: '📋' },
      { id: '8x1', label: '8×1排', icon: '📑' }
    ]
  },

  onLoad() {
    const app = getApp();
    const userPhoto = app.globalData.generatedPhoto || app.globalData.userPhoto;
    const selectedSpec = app.globalData.selectedSpec;
    const selectedColor = app.globalData.selectedColor;

    if (!userPhoto) {
      wx.showToast({ title: '没有照片', icon: 'none' });
      setTimeout(() => wx.navigateBack(), 1000);
      return;
    }

    const specTags = [];
    if (selectedSpec) {
      specTags.push(selectedSpec.name);
      if (selectedSpec.width && selectedSpec.height) {
        specTags.push(`${selectedSpec.width}×${selectedSpec.height}mm`);
      }
    }
    if (selectedColor) {
      specTags.push(`${selectedColor.name}底`);
    }

    this.setData({
      photoSrc: userPhoto,
      bgColorHex: selectedColor ? selectedColor.hex : '#ffffff',
      selectedColorId: selectedColor ? selectedColor.id : 'white',
      selectedSpecId: selectedSpec ? selectedSpec.id : '1inch_normal',
      specTags,
      colors: specs.BG_COLORS,
      allSpecs: specs.PHOTO_SPECS.filter(s => s.width) // 排除自定义
    });
  },

  // 切换底色
  changeColor(e) {
    const colorId = e.currentTarget.dataset.color;
    const color = specs.getColorById(colorId);
    if (!color) return;

    const app = getApp();
    const spec = app.globalData.selectedSpec || specs.getSpecById('1inch_normal');
    
    this.setData({ 
      selectedColorId: colorId,
      bgColorHex: color.hex 
    });

    app.globalData.selectedColor = color;

    // 重新生成照片
    wx.showLoading({ title: '换底色中...' });
    imageUtil.generateIDPhoto(app.globalData.userPhoto, spec, color.hex)
      .then((newPath) => {
        wx.hideLoading();
        app.globalData.generatedPhoto = newPath;
        this.setData({ photoSrc: newPath });
        
        // 更新标签
        const specTags = [spec.name, `${spec.width}×${spec.height}mm`, `${color.name}底`];
        this.setData({ specTags });
      })
      .catch(() => {
        wx.hideLoading();
        wx.showToast({ title: '换底色失败', icon: 'none' });
      });
  },

  // 切换尺寸
  changeSpec(e) {
    const specId = e.currentTarget.dataset.spec;
    const spec = specs.getSpecById(specId);
    if (!spec) return;

    const app = getApp();
    const color = app.globalData.selectedColor || specs.getColorById('white');

    this.setData({ selectedSpecId: specId });

    app.globalData.selectedSpec = spec;

    // 重新生成
    wx.showLoading({ title: '调整尺寸中...' });
    imageUtil.generateIDPhoto(app.globalData.userPhoto, spec, color.hex)
      .then((newPath) => {
        wx.hideLoading();
        app.globalData.generatedPhoto = newPath;
        this.setData({ photoSrc: newPath });
        
        const specTags = [spec.name, `${spec.width}×${spec.height}mm`, `${color.name}底`];
        this.setData({ specTags });
      })
      .catch(() => {
        wx.hideLoading();
        wx.showToast({ title: '调整失败', icon: 'none' });
      });
  },

  // 选择排版模式
  selectLayout(e) {
    const layoutId = e.currentTarget.dataset.layout;
    this.setData({ selectedLayout: layoutId });

    if (layoutId === 'single') {
      this.setData({ showPreview: false, previewSrc: null });
      return;
    }

    const app = getApp();
    const spec = app.globalData.selectedSpec || specs.getSpecById('1inch_normal');
    const userPhoto = app.globalData.generatedPhoto || app.globalData.userPhoto;

    const [cols, rows] = layoutId.split('x').map(Number);
    
    imageUtil.generateLayoutPhoto(userPhoto, spec, cols, rows)
      .then((path) => {
        this.setData({ showPreview: true, previewSrc: path });
      })
      .catch(() => {
        wx.showToast({ title: '排版生成失败', icon: 'none' });
      });
  },

  // 保存到相册
  savePhoto() {
    const path = this.data.previewSrc || this.data.photoSrc;
    if (!path) {
      wx.showToast({ title: '没有可保存的照片', icon: 'none' });
      return;
    }

    wx.showLoading({ title: '保存中...' });
    imageUtil.saveImageToAlbum(path)
      .then(() => wx.hideLoading())
      .catch(() => wx.hideLoading());
  },

  // 返回首页
  goBack() {
    wx.navigateBack();
  }
});
