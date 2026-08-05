// ====== 搜索证件照规格 ======
var specs = require('../../utils/specs.js');
var idPhotoEntry = require('../../utils/idPhotoEntry.js');

Page({
  data: {
    searchValue: '',
    filteredSpecs: [],
    currentCat: '',
    currentGroupId: '',
    currentGroupName: '',
    pageMode: 'home',
    showAllSearch: false,
    hiddenSearchCount: 0
  },

  onLoad: function(options) {
    var groupId = options.groupId || '';
    var cat = options.cat || '';
    if (groupId) {
      this.loadGroup(groupId);
      return;
    }
    this.loadHome(cat);
  },

  loadHome: function(cat) {
    var list = specs.getSpecGroupCards(cat || '全部');
    this.setData({
      pageMode: 'home',
      currentCat: cat || '',
      currentGroupId: '',
      currentGroupName: cat ? cat : '常用规格',
      searchValue: '',
      showAllSearch: false,
      hiddenSearchCount: 0,
      filteredSpecs: list
    });
    wx.setNavigationBarTitle({ title: '搜索证件照规格' });
  },

  loadGroup: function(groupId) {
    var group = specs.getGroupById(groupId);
    if (!group) {
      this.loadHome('');
      return;
    }
    function shortText(value) {
      var text = (value || '').toString().replace(/\s+/g, ' ').trim();
      return text.length > 38 ? text.slice(0, 38) + '...' : text;
    }
    var list = specs.getGroupSpecs(groupId).map(function(spec) {
        var sourceLevel = spec.sourceLevel || 'unknown';
        return {
        id: spec.id,
        type: 'spec',
        specId: spec.id,
        name: spec.displayName || spec.name,
        size: specs.formatSpecSize ? specs.formatSpecSize(spec) : [spec.mm, spec.px].filter(Boolean).join(' | '),
        fileText: spec.fileText || ((spec.fileFormat || ['jpg', 'jpeg']).join('/').toUpperCase()),
        sourceLevel: sourceLevel,
        sourceBadge: specs.getVisibleSourceBadge ? specs.getVisibleSourceBadge(sourceLevel) : ((specs.sourceLabels && specs.sourceLabels[sourceLevel]) || '按公告'),
        sourceClass: 'source-' + sourceLevel,
        note: '',
        icon: group.icon || '📷',
        thumbBg: '#e8f0fe',
        colors: (spec.colors || spec.bgColors || []).map(function(cid) {
          var c = specs.getColorById(cid);
          return { id: cid, hex: c ? c.hex : '#1a73e8' };
        }),
        badge: '',
        applicableText: shortText(spec.applicableText || (spec.appliesTo ? ('适用：' + spec.appliesTo) : ''))
      };
    });
    this.setData({
      pageMode: 'group',
      currentGroupId: groupId,
      currentGroupName: group.groupName,
      searchValue: '',
      showAllSearch: false,
      hiddenSearchCount: 0,
      filteredSpecs: list
    });
    wx.setNavigationBarTitle({ title: group.groupName });
  },

  onSearch: function(e) {
    var value = e.detail.value || '';
    if (!value.trim()) {
      if (this.data.currentGroupId) {
        this.loadGroup(this.data.currentGroupId);
      } else {
        this.loadHome(this.data.currentCat);
      }
      return;
    }
    var all = specs.searchSpecEntries(value);
    if (this.data.currentGroupId) {
      all = all.filter(function(item) {
        return item.groupId === this.data.currentGroupId;
      }, this);
    }
    var showAll = this.data.showAllSearch;
    this.setData({
      pageMode: 'search',
      searchValue: value,
      filteredSpecs: showAll ? all : all.slice(0, 8),
      hiddenSearchCount: Math.max(0, all.length - 8)
    });
    wx.setNavigationBarTitle({ title: '搜索结果' });
  },

  showMoreSearch: function() {
    var all = specs.searchSpecEntries(this.data.searchValue);
    if (this.data.currentGroupId) {
      all = all.filter(function(item) {
        return item.groupId === this.data.currentGroupId;
      }, this);
    }
    this.setData({
      showAllSearch: true,
      filteredSpecs: all,
      hiddenSearchCount: 0
    });
  },

  toggleFilter: function() {
    var that = this;
    wx.showActionSheet({
      itemList: ['全部', '常用证件照', '考试报名', '驾驶证 / 社保 / 身份证', '学籍 / 入学', '地方常用', '平台特殊 / 自定义'],
      success: function(res) {
        var cats = ['', '常用证件照', '考试报名', '驾驶证 / 社保 / 身份证', '学籍 / 入学', '地方常用', '平台特殊 / 自定义'];
        that.loadHome(cats[res.tapIndex]);
      }
    });
  },

  selectSpec: function(e) {
    var item = e.currentTarget.dataset.item;
    var type = e.currentTarget.dataset.type;
    var id = e.currentTarget.dataset.id;
    var groupId = e.currentTarget.dataset.group;
    var specId = e.currentTarget.dataset.spec;

    if ((item && item.type === 'custom') || type === 'custom' || id === 'custom_size') {
      wx.navigateTo({ url: '/pages/tool-detail/tool-detail?type=customSize' });
      return;
    }
    if ((item && item.type === 'group') || type === 'group') {
      wx.navigateTo({ url: '/pages/specs/specs?groupId=' + (groupId || id) });
      return;
    }
    idPhotoEntry.openCaptureGuide(specId || id);
  }
});
